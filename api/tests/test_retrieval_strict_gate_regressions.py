from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase

from agents.graph.edges import should_continue_after_retrieval
from agents.graph.nodes import generate_php_node
from agents.graph.state import create_initial_state


class _WeakRetriever:
    def __init__(self, user_id=None, analyzed_patterns=None):
        self.last_top_candidates = []
        self.last_retrieval_metrics = {
            'retrieval_score': 12.0,
            'real_db_function_count': 0,
            'synthetic_db_function_count': 7,
            'candidate_count': 0,
        }

    def get_php_examples(self, intent, k=3, user_request=''):
        self.last_retrieval_metrics = {
            'retrieval_score': 12.0,
            'real_db_function_count': 0,
            'synthetic_db_function_count': 7,
            'candidate_count': 0,
        }
        return "<?php // weak retrieval ?>"


class RetrievalStrictGateRegressionTests(SimpleTestCase):
    def test_retrieval_edge_routes_fail_when_gate_is_blocked(self):
        self.assertEqual(
            should_continue_after_retrieval({'retrieval_gate_blocked': True, 'retrieval_gate_reason': 'x'}),
            'fail',
        )
        self.assertEqual(
            should_continue_after_retrieval({'retrieval_gate_blocked': False}),
            'continue',
        )

    def test_generate_php_blocks_before_generation_when_retrieval_floor_fails(self):
        state = create_initial_state(
            user_request='Create Student form in strict mode',
            project_id='p1',
            user_id='8',
            codebase_id='cb1',
        )
        state['intent'] = {
            'database': {'table_name': 'tblstudent'},
            'fields': [{'name': 'STU_CODE'}, {'name': 'AdmissionNo'}],
        }
        state['strict_contract'] = {
            'valid': True,
            'master_table': 'tblstudent',
            'file_name': 'frmStudent.php',
            'title': 'Student',
            'primary_key': 'STU_CODE',
            'master_fields': [{'name': 'STU_CODE'}, {'name': 'AdmissionNo'}],
            'detail_fields': [],
            'features': [],
        }
        state['analyzed_patterns'] = {'php': {'functions': []}}

        with patch.object(generate_php_node, '_initialize', return_value=None), patch(
            'agents.utils.enterprise_pattern_retriever.EnterprisePatternRetriever',
            _WeakRetriever,
        ):
            out = async_to_sync(generate_php_node.execute)(state)

        self.assertTrue(out.get('retrieval_gate_blocked'))
        self.assertEqual(out.get('current_step'), 'retrieval_blocked')
        self.assertEqual(out.get('status'), 'failed')
        self.assertIn('Retrieval quality below strict floor', out.get('validation_reason') or '')
        self.assertIn('Retrieval quality below strict floor', out.get('error_message') or '')
