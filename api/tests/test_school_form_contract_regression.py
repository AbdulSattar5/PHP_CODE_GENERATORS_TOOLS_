from pathlib import Path

from django.test import SimpleTestCase

from agents.validators.company_form_contract_validator import CompanyFormContractValidator
from agents.validators.syntax_validator import SyntaxValidator


SCHOOL_FORM_PATH = Path(__file__).resolve().parent / 'fixtures' / 'generated' / 'frmSchool.php'


class SchoolFormContractRegressionTests(SimpleTestCase):
    def test_school_form_file_exists(self):
        self.assertTrue(SCHOOL_FORM_PATH.exists(), f'Missing file: {SCHOOL_FORM_PATH}')

    def test_school_form_passes_company_contract_validator(self):
        code = SCHOOL_FORM_PATH.read_text(encoding='utf-8', errors='ignore')
        result = CompanyFormContractValidator().validate(code)
        self.assertTrue(result.get('passed', False), result.get('errors', []))

    def test_school_form_has_valid_php_syntax(self):
        code = SCHOOL_FORM_PATH.read_text(encoding='utf-8', errors='ignore')
        result = SyntaxValidator().validate_php(code)
        self.assertTrue(result.get('valid', False), result.get('errors', []))
