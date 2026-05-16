from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from agents.utils.strict_erp_controller import PatternMemoryService, StrictERPController
from models.project import CompanyCodebase, PatternLearningEvent, PatternMemory, Project


class DummyWorkflow:
    def __init__(self, payload):
        self.payload = payload

    async def execute(self, **kwargs):
        return self.payload


STRICT_PROMPT = """Create complete Student master-detail form.

Table: tblstudent
Detail Table: tblstudentsubjectdt
File name: frmStudent.php
Title: Student
Primary Key: STU_CODE

Master Fields:
- STU_CODE | DB: VARCHAR(20) | Input: readonly textbox | Required: Yes
- AdmissionNo | DB: VARCHAR(30) | Input: textbox | Required: Yes

Detail Grid:
- SR_NO | DB: INT | Input: readonly textbox | Required: Yes
- Subject_Code | DB: VARCHAR(20) | Input: select | Required: Yes

Relationships:
- Subject_Code -> tblsubject.Subject_Code | Input: select | Cascade: Yes

Dependencies:
- tblattendance | field=STU_CODE | message=Cannot delete attendance rows.

Required Company Patterns:
- AJAX GetMaxID handler + maxid() JS
- detail-grid insert/update/delete flow using TXTCOUNTACC and row loop
- formValidation
- select2
"""

STRICT_COMPACT_PROMPT = (
    "Create complete Student master-detail form. "
    "Master Table: tblstudent "
    "Detail Table: tblstudentsubjectdt "
    "File name: frmStudent.php "
    "Title: Student "
    "Primary Key: - STU_CODE | DB: VARCHAR(20) PRIMARY KEY | Input: readonly textbox "
    "Master Fields: "
    "- STU_CODE | DB: VARCHAR(20) | Input: readonly textbox | Required: Yes "
    "- AdmissionNo | DB: VARCHAR(30) | Input: textbox | Required: Yes "
    "- Campus_Code | DB: VARCHAR(20) | Input: select | Required: Yes "
    "- Class_Code | DB: VARCHAR(20) | Input: select | Required: Yes "
    "- Section_Code | DB: VARCHAR(20) | Input: select | Required: Yes "
    "- First_Name | DB: VARCHAR(120) | Input: textbox | Required: Yes "
    "- Father_Name | DB: VARCHAR(150) | Input: textbox | Required: Yes "
    "- DOB | DB: DATE | Input: date | Required: Yes "
    "- Admission_Date | DB: DATE | Input: date | Required: Yes "
    "- STATUS | DB: TINYINT(1) | Input: checkbox | Required: No "
    "Detail Grid (tblstudentsubjectdt): "
    "- SR_NO | DB: INT | Input: readonly textbox | Required: Yes "
    "- Subject_Code | DB: VARCHAR(20) | Input: select | Required: Yes "
    "- Subject_Name | DB: VARCHAR(120) | Input: readonly textbox | Required: No "
    "- Is_Optional | DB: TINYINT(1) | Input: checkbox | Required: No "
    "Relationships: - Subject_Code -> tblsubject.Subject_Code | Input: select | Cascade: Yes "
    "Dependencies: "
    "- tblattendance | field=STU_CODE | message=Cannot delete attendance rows. "
    "- tblstudentfee | field=STU_CODE | message=Cannot delete fee rows. "
    "Required Company Patterns: "
    "- AJAX GetMaxID handler + maxid() JS "
    "- detail-grid insert/update/delete flow using TXTCOUNTACC and row loop "
    "- formValidation - select2"
)


def sample_analyzed_patterns():
    return {
        'php': {
            'functions': [
                'db_insert',
                'db_update',
                'db_delete',
                'db_getRecord',
                'getrows',
                'getrows2',
                'getvalue',
                'funStartTran',
                'funEndTran',
                'fun_log',
            ],
            'table_names': ['tblstudent', 'tblstudentsubjectdt', 'tblsubject'],
            'field_names': ['STU_CODE', 'AdmissionNo', 'SR_NO', 'Subject_Code', 'TXTCOUNTACC'],
            'ajax_functions': ['GetMaxID', 'GetCOSTCENTER'],
            'include_patterns': ['config.php', 'topmenu.php', 'sidemenu.php', 'footer.php'],
            'session_management': "$_SESSION['user_id']; $_SESSION['comp_code']; $_SESSION['login_id'];",
            'transaction_management': {'start': 'funStartTran', 'end': 'funEndTran'},
            'formvalidation': {'has_formvalidation': True, 'form_selector': '#entryform'},
            'grid_patterns': [{'name': 'TXTCOUNTACC detail loop'}],
            'dynamic_dropdowns': [{'name': 'Campus_Class_Section'}],
        },
        'html': {
            'css_classes': ['form-horizontal', 'select2', 'control-label'],
            'form_structure': ['<form class="form-horizontal">'],
        },
        'js': {},
    }


class StrictERPControllerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='strict_controller_user',
            password='pass1234',
            email='strict-controller@example.com',
        )
        self.codebase = CompanyCodebase.objects.create(
            user=self.user,
            name='Strict Codebase',
            upload_path='company_codebases/strict.zip',
            is_indexed=True,
            total_files=20,
            indexed_files=20,
        )
        self.controller = StrictERPController()
        self.memory_service = PatternMemoryService()

    def test_bootstrap_creates_structured_pattern_memory(self):
        created = self.memory_service.bootstrap_from_analyzed_patterns(
            user_id=str(self.user.id),
            codebase_id=str(self.codebase.id),
            analyzed_patterns=sample_analyzed_patterns(),
        )

        self.assertGreaterEqual(len(created), 6)
        pattern_types = set(
            PatternMemory.objects.filter(codebase=self.codebase).values_list('pattern_type', flat=True)
        )
        self.assertIn('CRUD_PATTERN', pattern_types)
        self.assertIn('MASTER_DETAIL_PATTERN', pattern_types)
        self.assertIn('AJAX_PATTERN', pattern_types)
        self.assertIn('VALIDATION_PATTERN', pattern_types)
        self.assertIn('SELECT2_PATTERN', pattern_types)

    def test_strict_contract_separates_master_and_detail_fields(self):
        contract = self.controller.contract_parser.parse(STRICT_PROMPT)

        self.assertTrue(contract['valid'])
        self.assertEqual(contract['form_type'], 'MASTER_DETAIL')
        self.assertEqual([field['name'] for field in contract['master_fields']], ['STU_CODE', 'AdmissionNo'])
        self.assertEqual([field['name'] for field in contract['detail_fields']], ['SR_NO', 'Subject_Code'])

    def test_strict_contract_is_deterministic_for_compact_prompt(self):
        contract = self.controller.contract_parser.parse(STRICT_COMPACT_PROMPT)

        self.assertTrue(contract['valid'])
        self.assertEqual(contract['file_name'], 'frmStudent.php')
        self.assertEqual(contract['title'], 'Student')
        self.assertEqual(contract['master_table'], 'tblstudent')
        self.assertEqual(contract['detail_table'], 'tblstudentsubjectdt')
        self.assertEqual(contract['primary_key'], 'STU_CODE')
        self.assertEqual(contract['form_type'], 'MASTER_DETAIL')
        self.assertEqual(
            [field['name'] for field in contract['master_fields']],
            [
                'STU_CODE', 'AdmissionNo', 'Campus_Code', 'Class_Code', 'Section_Code',
                'First_Name', 'Father_Name', 'DOB', 'Admission_Date', 'STATUS',
            ],
        )
        self.assertEqual(
            [field['name'] for field in contract['detail_fields']],
            ['SR_NO', 'Subject_Code', 'Subject_Name', 'Is_Optional'],
        )
        self.assertEqual(len(contract['dependencies']), 2)

    def test_preflight_rejects_when_pattern_memory_is_missing(self):
        result = self.controller.run_preflight(
            user_request=STRICT_PROMPT,
            user_id=str(self.user.id),
            codebase_id=str(self.codebase.id),
            analyzed_patterns=None,
        )

        self.assertFalse(result['approved'])
        self.assertEqual(result['reason'], 'missing_memory')
        self.assertTrue(result['metadata']['hard_block'])
        self.assertEqual(result['result']['validation_result']['block_generation'], True)

    def test_preflight_blocks_low_pattern_coverage(self):
        PatternMemory.objects.create(
            user=self.user,
            codebase=self.codebase,
            pattern_type='CRUD_PATTERN',
            form_type='ALL',
            feature_signature='crud',
            payload={'tables': ['tblstudent']},
            required_functions=['db_insert', 'db_update', 'db_delete'],
            structure_skeleton={'crud_handlers': ['Save', 'Update', 'Delete']},
            constraints=['Use company db functions only'],
            examples=['db_insert', 'db_update', 'db_delete'],
        )

        result = self.controller.run_preflight(
            user_request=STRICT_PROMPT,
            user_id=str(self.user.id),
            codebase_id=str(self.codebase.id),
            analyzed_patterns=None,
        )

        self.assertFalse(result['approved'])
        self.assertEqual(result['reason'], 'pattern_coverage_below_floor')
        self.assertLess(result['retrieval']['pattern_coverage'], 0.75)
        self.assertTrue(result['metadata']['hard_block'])

    def test_contamination_outcome_blacklists_combo_and_decreases_weight(self):
        created = self.memory_service.bootstrap_from_analyzed_patterns(
            user_id=str(self.user.id),
            codebase_id=str(self.codebase.id),
            analyzed_patterns=sample_analyzed_patterns(),
        )
        record = created[0]
        before_weight = record.weight

        retrieval = self.memory_service.retrieve(
            user_id=str(self.user.id),
            codebase_id=str(self.codebase.id),
            contract=self.controller.contract_parser.parse(STRICT_PROMPT),
        )

        event = self.memory_service.record_outcome(
            user_id=str(self.user.id),
            codebase_id=str(self.codebase.id),
            project_id=None,
            contract=self.controller.contract_parser.parse(STRICT_PROMPT),
            retrieval=retrieval,
            outcome='contamination',
            phase='validation',
            failure_reason='cross-entity contamination detected',
            validator_errors=['contamination'],
            section_sizes={'complete_php': 0},
            metadata={'test_case': 'contamination'},
        )

        record.refresh_from_db()
        self.assertIsNotNone(event)
        self.assertTrue(event.is_blacklisted_combo)
        self.assertLess(record.weight, before_weight)
        self.assertEqual(record.contamination_count, 1)
        self.assertEqual(
            PatternLearningEvent.objects.filter(codebase=self.codebase, is_blacklisted_combo=True).count(),
            1,
        )


@override_settings(
    ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'],
    SECURE_SSL_REDIRECT=False,
)
class StrictERPGatingApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='strict_api_user',
            password='pass1234',
            email='strict-api@example.com',
        )
        self.project = Project.objects.create(
            user=self.user,
            name='Strict API Project',
            description='Strict ERP API gating tests',
        )
        self.client = APIClient()
        self.client.login(username='strict_api_user', password='pass1234')

    def test_hard_block_metadata_prevents_fallback(self):
        workflow_result = {
            'error': 'Pattern memory is empty for the selected codebase.',
            'details': 'Run codebase analysis before generation.',
            'code': {},
            'status': 'failed',
            'validation_result': {
                'approval_status': 'needs_revision',
                'validation_passed': False,
                'block_save': True,
                'block_generation': True,
                'needs_revision': True,
                'validation_reason': 'missing_memory',
            },
            'metadata': {
                'strict_erp': {
                    'approved': False,
                    'hard_block': True,
                    'retrieval_quality': 0.0,
                    'pattern_coverage': 0.0,
                }
            },
        }

        with patch('api.views.AGENTS_AVAILABLE', True), patch(
            'api.views.code_generation_workflow',
            DummyWorkflow(workflow_result),
        ):
            response = self.client.post(
                '/api/generate/',
                {
                    'user_request': STRICT_PROMPT,
                    'project_id': str(self.project.id),
                    'use_company_patterns': True,
                    'use_standards': True,
                    'auto_execute_sql': False,
                },
                format='json',
            )

        self.assertEqual(response.status_code, 422)
        data = response.json()
        self.assertEqual(data['status'], 'error')
        self.assertFalse(data['fallback_used'])
        self.assertEqual(data['generated_files'].get('complete_php', ''), '')
        self.assertIn('strict', data['message'].lower())
