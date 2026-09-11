from pathlib import Path
import io
import zipfile

from fastapi.testclient import TestClient

from backend.app.main import app, UPLOADS_DIR


def test_core_workflow():
    with TestClient(app) as client:
        assert client.post('/api/admin/reset').status_code == 200

        health = client.get('/api/health')
        assert health.status_code == 200
        assert health.json() == {
            'status': 'ok',
            'version': '当前',
            'database': 'verification.db',
        }

        project = client.get('/api/project').json()
        assert project['name'] == '通信接入网建设项目'
        assert project['data_version'] == '工程数据集'

        summary = client.get('/api/summary').json()
        assert summary['kpis']['object_total'] == 30
        assert summary['kpis']['evidence_total'] == 57
        assert summary['kpis']['verified'] == 5
        assert summary['kpis']['partial'] == 15
        assert summary['kpis']['missing'] == 10
        assert summary['kpis']['open_issues'] == 94
        assert sum(x['value'] for x in summary['status_distribution']) == 30
        issue_counts = {x['name']: x['value'] for x in summary['issue_distribution']}
        assert issue_counts['编码未匹配'] == 4
        assert issue_counts['对象未关联'] if '对象未关联' in issue_counts else 0 == 0

        gis = client.get('/api/gis').json()
        assert len(gis['objects']) == 30
        assert any(f['layer'] == 'CABLE' for f in gis['features'])
        assert any(f['layer'] == 'INFRASTRUCTURE' for f in gis['features'])
        assert any(f['layer'] == 'PTECH' for f in gis['features'])
        assert any(f['layer'] == 'SITE' for f in gis['features'])

        target = 'PBO-JAD-MAR-0021'
        before = client.get(f'/api/objects/{target}').json()['result']
        assert before['matched_count'] == 0

        source = Path('backend/assets/raw/IMG_20220330_101406.jpg')
        filename = f'{target}_site_overview.jpg'
        with source.open('rb') as fh:
            uploaded = client.post(
                '/api/evidence/upload',
                files={'file': (filename, fh, 'image/jpeg')},
                data={'source_type': '现场照片'},
            )
        assert uploaded.status_code == 200, uploaded.text
        evidence = uploaded.json()
        assert evidence['review_status'] == '待确认'
        assert evidence['match_method'] == '文件名解析+规则推断'
        assert evidence['candidates'][0]['object_id'] == target
        assert evidence['candidates'][0]['score'] >= 90

        confirmed = client.post(
            f"/api/evidence/{evidence['evidence_id']}/confirm-link",
            json={'object_id': target, 'confidence_score': 0.95, 'match_reason': '编码与证据类型一致，人工确认'},
        )
        assert confirmed.status_code == 200, confirmed.text
        verification = confirmed.json()['verification']
        assert verification['matched_count'] == 1
        assert verification['status'] == '部分匹配'

        issue = client.get('/api/issues', params={'object_id': target}).json()[0]
        updated = client.patch(
            f"/api/issues/{issue['issue_id']}",
            json={'status': '待整改', 'assignee': '施工队A', 'due_date': '2026-07-20', 'resolution_note': '已生成补证任务'},
        )
        assert updated.status_code == 200
        assert updated.json()['status'] == '待整改'

        excel = client.get('/api/exports/excel')
        assert excel.status_code == 200
        assert excel.headers['content-type'].startswith('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        assert len(excel.content) > 10_000
        with zipfile.ZipFile(io.BytesIO(excel.content)) as archive:
            workbook_xml = archive.read('xl/workbook.xml').decode('utf-8')
            assert '项目概览' in workbook_xml
            assert '对象验真台账' in workbook_xml

        pdf = client.get('/api/exports/pdf')
        assert pdf.status_code == 200
        assert pdf.headers['content-type'].startswith('application/pdf')
        assert pdf.content.startswith(b'%PDF')
        assert len(pdf.content) > 5_000

        video_path = Path('demo_upload/PBO-JAD-MAR-0008_site_inspection.mp4')
        with video_path.open('rb') as fh:
            video_result = client.post(
                '/api/evidence/upload-video',
                files={'file': (video_path.name, fh, 'video/mp4')},
                data={'evidence_type': 'site_overview', 'detected_code': 'PBO-JAD-MAR-0008'},
            )
        assert video_result.status_code == 200, video_result.text
        video_payload = video_result.json()
        assert video_payload['interval_seconds'] == 2.0
        assert video_payload['extracted_frame_count'] == 5
        assert all(frame['media_type'] == 'video_frame' for frame in video_payload['frames'])
        frame = video_payload['frames'][0]
        assert frame['review_status'] == '待确认'
        frame_confirm = client.post(
            f"/api/evidence/{frame['evidence_id']}/confirm-link",
            json={'object_id': 'PBO-JAD-MAR-0008', 'confidence_score': 0.99, 'match_reason': '视频帧人工确认'},
        )
        assert frame_confirm.status_code == 200
        assert frame_confirm.json()['evidence']['linked_object_id'] == 'PBO-JAD-MAR-0008'

        delivery = client.get('/api/exports/archive')
        assert delivery.status_code == 200
        assert delivery.headers['content-type'].startswith('application/zip')
        with zipfile.ZipFile(io.BytesIO(delivery.content)) as archive:
            names = set(archive.namelist())
            assert 'manifest.json' in names
            assert 'reports/验真报告.pdf' in names
            assert 'reports/验真数据.xlsx' in names
            assert 'data/objects.json' in names
            assert any(name.startswith('evidence/') for name in names)

        assert client.post('/api/admin/reset').status_code == 200

    for path in sorted(UPLOADS_DIR.rglob('*'), reverse=True):
        if path.is_file():
            path.unlink()
        elif path.is_dir() and path != UPLOADS_DIR:
            try:
                path.rmdir()
            except OSError:
                pass
