import os
from unittest import skipUnless

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase

from agents.graph.workflow import code_generation_workflow


STUDENT_PROMPT = """Create complete Student master-detail form.

Master Table: tblstudent
Detail Table: tblstudentsubjectdt
File name: frmStudent.php
Title: Student
CaseType: Student

Primary Key:
- STU_CODE | DB: VARCHAR(20) PRIMARY KEY | Input: readonly textbox

Master Fields (USE EXACT NAMES, NO EXTRA FIELDS):
- STU_CODE | DB: VARCHAR(20) | Input: readonly textbox | Required: Yes
- AdmissionNo | DB: VARCHAR(30) | Input: textbox | Required: Yes
- Campus_Code | DB: VARCHAR(20) | Input: select | Required: Yes
- Class_Code | DB: VARCHAR(20) | Input: select | Required: Yes
- Section_Code | DB: VARCHAR(20) | Input: select | Required: Yes
- First_Name | DB: VARCHAR(120) | Input: textbox | Required: Yes
- Father_Name | DB: VARCHAR(150) | Input: textbox | Required: Yes
- DOB | DB: DATE | Input: date | Required: Yes
- Admission_Date | DB: DATE | Input: date | Required: Yes
- STATUS | DB: TINYINT(1) | Input: checkbox | Required: No

Detail Grid (tblstudentsubjectdt):
- SR_NO | DB: INT | Input: readonly textbox | Required: Yes
- Subject_Code | DB: VARCHAR(20) | Input: select | Required: Yes
- Subject_Name | DB: VARCHAR(120) | Input: readonly textbox | Required: No
- Is_Optional | DB: TINYINT(1) | Input: checkbox | Required: No

Dependencies (Pre-Delete Checks):
- tblattendance | field=STU_CODE | message=Cannot delete. Attendance records exist.
- tblstudentfee | field=STU_CODE | message=Cannot delete. Fee records exist.

Required Company Patterns (MANDATORY):
- db_insert, db_update, db_delete, db_getRecord, getrows, getvalue
- AJAX GetMaxID handler + maxid() JS
- AJAX GetCOSTCENTER handler
- detail-grid insert/update/delete flow using TXTCOUNTACC and row loop
- Pre-delete dependency checks using getrows()
"""


@skipUnless(
    os.getenv("RUN_REAL_PIPELINE_TESTS") == "1",
    "Set RUN_REAL_PIPELINE_TESTS=1 to run real end-to-end pipeline test."
)
class StudentFullPipelineE2ETests(SimpleTestCase):
    """
    Real pipeline test (no DummyWorkflow / no hardcoded generated payload).
    Uses actual workflow + configured LLM backend.
    """

    def test_student_prompt_generates_complete_php_with_required_patterns(self):
        result = async_to_sync(code_generation_workflow.execute)(
            user_request=STUDENT_PROMPT,
            project_id=os.getenv("E2E_PROJECT_ID", "42b3e644-a6b1-4669-8500-43ce32ac33d2"),
            user_id=os.getenv("E2E_USER_ID", "8"),
            codebase_id=os.getenv("E2E_CODEBASE_ID", "371234c6-8f14-409d-ab06-f96a97d25a26"),
        )

        self.assertIsInstance(result, dict)
        self.assertFalse(result.get("error"), msg=str(result.get("details") or result))

        php = ((result.get("code") or {}).get("complete_php") or "")
        self.assertGreater(len(php), 8000, msg="Generated PHP is unexpectedly tiny")

        required_tokens = [
            "db_insert",
            "db_update",
            "db_delete",
            "db_getRecord",
            "getrows",
            "getvalue",
            "GetMaxID",
            "function maxid(",
            "GetCOSTCENTER",
            "TXTCOUNTACC",
            "tblattendance",
            "tblstudentfee",
            "STU_CODE",
            "AdmissionNo",
            "Campus_Code",
            "Class_Code",
            "Section_Code",
            "First_Name",
            "Father_Name",
            "DOB",
            "Admission_Date",
            "STATUS",
            "SR_NO",
            "Subject_Code",
            "Subject_Name",
            "Is_Optional",
        ]
        for token in required_tokens:
            self.assertIn(token, php, msg=f"Missing required token in output: {token}")
