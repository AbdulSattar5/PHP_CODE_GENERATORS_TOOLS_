import logging
from uuid import uuid4
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from models.project import CompanyCodebase, Project


class DummyWorkflow:
    def __init__(self, payload):
        self.payload = payload

    async def execute(self, **kwargs):
        return self.payload


class CapturingWorkflow:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        return self.payload


class FailingWorkflow:
    def __init__(self, message):
        self.message = message

    async def execute(self, **kwargs):
        raise ValueError(self.message)


@override_settings(
    ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'],
    SECURE_SSL_REDIRECT=False
)
class GenerateResponseContractTests(TestCase):
    def setUp(self):
        self._old_disable_level = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        self.user = User.objects.create_user(
            username='contract_user',
            password='pass1234',
            email='contract@example.com'
        )
        self.project = Project.objects.create(
            user=self.user,
            name='Contract Project',
            description='Response contract tests'
        )
        self.client = APIClient()
        self.client.login(username='contract_user', password='pass1234')

    def tearDown(self):
        logging.disable(self._old_disable_level)

    def _post_generate(self, user_request='create test form'):
        return self.client.post(
            '/api/generate/',
            {
                'user_request': user_request,
                'project_id': str(self.project.id),
                'use_company_patterns': True,
                'use_standards': True,
                'auto_execute_sql': False
            },
            format='json'
        )

    def _success_payload(self, file_name=None):
        file_name = file_name or f"frm_{uuid4().hex[:10]}.php"
        large_php = '<?php\n' + ('echo "ok";\n' * 1200) + '?>'
        return {
            'code': {'complete_php': large_php},
            'validation_score': 93,
            'validation_result': {
                'mode': 'strict_ok',
                'approval_status': 'approved',
                'validation_passed': True,
                'block_save': False,
                'block_generation': False,
                'needs_revision': False,
                'regeneration_required': False,
            },
            'metadata': {
                'generation_type': 'complete_php_only',
                'attempts_made': 1,
                'max_attempts': 3,
                'refusal_count': 0,
                'llm_call_failures': 0
            },
            'file_structure': {'files': {'complete_php': {'path': file_name}}},
            'deployment_guide': ''
        }

    def test_tiny_workflow_output_stays_hard_failure_without_fallback(self):
        workflow_result = {
            'code': {'complete_php': '<?php echo "tiny"; ?>'},
            'validation_score': 95,
            'validation_result': {'mode': 'ok', 'approval_status': 'needs_revision', 'validation_passed': False},
            'metadata': {
                'generation_type': 'complete_php_only',
                'attempts_made': 3,
                'max_attempts': 3,
                'refusal_count': 2,
                'llm_call_failures': 0
            },
            'file_structure': {'files': {'complete_php': {'path': 'frmTiny.php'}}},
            'deployment_guide': ''
        }

        with patch('api.views.AGENTS_AVAILABLE', True), patch('api.views.code_generation_workflow', DummyWorkflow(workflow_result)):
            response = self._post_generate('force tiny output fallback')

        self.assertEqual(response.status_code, 422)
        data = response.json()
        self.assertEqual(data['status'], 'error')
        self.assertFalse(data['fallback_used'])
        self.assertEqual(data['generated_files'].get('complete_php', ''), '')
        self.assertEqual(data['metadata'].get('attempts_made'), 3)
        self.assertEqual(data['metadata'].get('refusal_count'), 2)
        self.assertIn('strict validation', data['message'].lower())

    def test_large_clean_workflow_output_stays_success(self):
        workflow_result = self._success_payload('frmClean.php')

        with patch('api.views.AGENTS_AVAILABLE', True), patch('api.views.code_generation_workflow', DummyWorkflow(workflow_result)):
            response = self._post_generate('clean success path')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'success')
        self.assertFalse(data['fallback_used'])

    def test_inline_fallback_mode_in_metadata_marks_warning(self):
        large_php = '<?php\n' + ('echo "warn";\n' * 1200) + '?>'
        workflow_result = {
            'code': {'complete_php': large_php},
            'validation_score': 90,
            'validation_result': {
                'mode': 'strict_ok',
                'approval_status': 'approved',
                'validation_passed': True,
                'block_save': False,
                'block_generation': False,
                'needs_revision': False,
                'regeneration_required': False,
            },
            'metadata': {
                'generation_type': 'complete_php_only',
                'inline_generation_metadata': {
                    'fallback_mode': 'company_template',
                    'attempts_made': 2,
                    'max_attempts': 3,
                    'refusal_count': 1,
                    'llm_call_failures': 0
                },
                'attempts_made': 2,
                'max_attempts': 3,
                'refusal_count': 1,
                'llm_call_failures': 0
            },
            'file_structure': {'files': {'complete_php': {'path': 'frmWarn.php'}}},
            'deployment_guide': ''
        }

        with patch('api.views.AGENTS_AVAILABLE', True), patch('api.views.code_generation_workflow', DummyWorkflow(workflow_result)):
            response = self._post_generate('metadata fallback mode warning')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['status'], 'warning')
        self.assertTrue(data['fallback_used'])

    def test_auto_selects_best_indexed_codebase_when_request_omits_codebase(self):
        lower_indexed = CompanyCodebase.objects.create(
            user=self.user,
            name='Indexed Small',
            upload_path='dummy/path/a.zip',
            is_indexed=True,
            total_files=100,
            indexed_files=40
        )
        higher_indexed = CompanyCodebase.objects.create(
            user=self.user,
            name='Indexed Large',
            upload_path='dummy/path/b.zip',
            is_indexed=True,
            total_files=120,
            indexed_files=95
        )
        self.assertNotEqual(str(lower_indexed.id), str(higher_indexed.id))

        workflow = CapturingWorkflow(self._success_payload('frmAuto.php'))
        with patch('api.views.AGENTS_AVAILABLE', True), patch('api.views.code_generation_workflow', workflow):
            response = self._post_generate('create customer form without explicit codebase id')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(workflow.calls), 1)
        self.assertEqual(workflow.calls[0].get('codebase_id'), str(higher_indexed.id))

    def test_rejects_foreign_codebase_and_proceeds_without_it(self):
        other_user = User.objects.create_user(
            username='other_user',
            password='pass1234',
            email='other@example.com'
        )
        foreign_codebase = CompanyCodebase.objects.create(
            user=other_user,
            name='Foreign',
            upload_path='dummy/path/foreign.zip',
            is_indexed=True,
            total_files=22,
            indexed_files=22
        )
        workflow = CapturingWorkflow(self._success_payload('frmForeignIgnored.php'))
        with patch('api.views.AGENTS_AVAILABLE', True), patch('api.views.code_generation_workflow', workflow):
            response = self.client.post(
                '/api/generate/',
                {
                    'user_request': 'create area form',
                    'project_id': str(self.project.id),
                    'codebase_id': str(foreign_codebase.id),
                    'use_company_patterns': True,
                    'use_standards': True,
                    'auto_execute_sql': False
                },
                format='json'
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(workflow.calls), 1)
        self.assertIsNone(workflow.calls[0].get('codebase_id'))

    def test_fallback_diagnostics_infers_attempts_from_exception_message(self):
        failing = FailingWorkflow("LLM refused to generate ERP code after 3 attempts.")
        with patch('api.views.AGENTS_AVAILABLE', True), patch('api.views.code_generation_workflow', failing):
            response = self._post_generate('trigger inference from exception')

        self.assertEqual(response.status_code, 422)
        data = response.json()
        self.assertEqual(data['status'], 'error')
        self.assertEqual((data['metadata'] or {}).get('attempts_made'), 3)
        self.assertEqual((data['metadata'] or {}).get('refusal_count'), 3)

    def test_persistence_integrity_failure_blocks_save_and_returns_422(self):
        filler = 'echo "x";\n' * 1200
        malformed_code = """<?php $form='frmStudent.php'; $form2='frmStudent.php'; ?>
{filler}
<html>
<head>
<script>
document.onkeydown = checkKeycode
{{
    return true;
}}
</script>
</head>
<body>
<form id="frm" name="frm" method="POST" action="<?=$form2;?>" enctype="multipart/form-data">
">
<input name="STU_CODE" />
</form>
</body>
</html>
""".format(filler=filler)
        workflow_result = {
            'code': {'complete_php': malformed_code},
            'validation_score': 95,
            'validation_result': {
                'mode': 'strict_ok',
                'approval_status': 'approved',
                'validation_passed': True,
                'block_save': False,
                'block_generation': False,
                'needs_revision': False,
                'regeneration_required': False,
            },
            'metadata': {'generation_type': 'complete_php_only'},
            'file_structure': {'files': {'complete_php': {'path': 'frmStudent.php'}}},
            'deployment_guide': ''
        }

        with (
            patch('api.views.AGENTS_AVAILABLE', True),
            patch('api.views.code_generation_workflow', DummyWorkflow(workflow_result)),
            patch('api.views.CodeGenerationViewSet._save_generated_code') as mocked_save
        ):
            response = self._post_generate('force malformed output to test persistence gate')

        self.assertEqual(response.status_code, 422)
        data = response.json()
        self.assertEqual(data['status'], 'error')
        self.assertEqual(data.get('validation_reason'), 'persistence_integrity_failed')
        self.assertFalse(data['validation_result'].get('validation_passed', True))
        self.assertTrue(data['validation_result'].get('block_save', False))
        mocked_save.assert_not_called()
