"""
Dynamic Pattern Analyzer
Analyzes company codebase and extracts actual patterns automatically
NO HARDCODED PATTERNS - Everything learned from uploaded code
"""

import re
import logging
from typing import Dict, List, Set
from collections import Counter
from agents.vectorstore.embeddings import CodeEmbeddingManager

logger = logging.getLogger(__name__)


class CodebasePatternAnalyzer:
    """
    Analyzes uploaded company codebase to extract REAL patterns
    Replaces hardcoded dummy patterns with actual company code patterns
    """
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.embedding_manager = CodeEmbeddingManager(user_id=user_id)
    
    def analyze_codebase_patterns_sync(self, codebase_id: str) -> Dict:
        """
        🆕 FIXED: Synchronous version of pattern analysis for background threads
        Avoids event loop issues when called from background threads
        """
        logger.info(f"🔍 Analyzing codebase {codebase_id} for patterns (SYNC)...")
        
        # 🆕 DIAGNOSTIC: Check vectorstore status
        logger.info("🔍 DIAGNOSTIC: Checking vectorstore status...")
        try:
            total_docs = self.embedding_manager.get_vectorstore_stats()
            logger.info(f"   Total documents in vectorstore: {total_docs}")
        except Exception as e:
            logger.error(f"   Error checking vectorstore: {e}")
        
        patterns = {
            'php': self._analyze_php_patterns_sync(codebase_id),
            'html': self._analyze_html_patterns_sync(codebase_id),
            'css': self._analyze_css_patterns_sync(codebase_id),
            'js': self._analyze_js_patterns_sync(codebase_id),
            'sql': self._analyze_sql_patterns_sync(codebase_id)
        }
        
        logger.info(f"✅ Pattern analysis complete for {codebase_id}")
        return patterns
    
    def _analyze_php_patterns_sync(self, codebase_id: str) -> Dict:
        """
        🆕 UNIFIED INLINE PHP ANALYSIS
        Analyzes complete inline PHP files (PHP + HTML + CSS + JS in one file)
        This matches company codebase structure where everything is inline
        """
        logger.info(f"🔍 Starting UNIFIED PHP pattern analysis (SYNC) for codebase: {codebase_id}")
        logger.info(f"   📋 Analyzing inline PHP files (PHP + HTML + CSS + JS)")
        
        # Get PHP documents directly from collection
        php_codes = []
        try:
            logger.info(f"🔍 Attempting direct collection access...")
            collection = self.embedding_manager.vectorstore._collection
            all_docs = collection.get()
            
            if all_docs and all_docs.get('documents'):
                logger.info(f"   Total documents in collection: {len(all_docs['documents'])}")
                
                # Filter for PHP documents (which contain inline HTML/CSS/JS)
                for i, doc in enumerate(all_docs['documents']):
                    metadata = all_docs['metadatas'][i] if all_docs.get('metadatas') else {}
                    
                    # Check if this is a PHP file AND belongs to current codebase
                    if (metadata.get('language') == 'php' and 
                        metadata.get('codebase_id') == codebase_id):
                        php_codes.append({
                            'content': doc,
                            'metadata': metadata
                        })
                
                logger.info(f"🔍 Direct access found {len(php_codes)} PHP documents for codebase {codebase_id}")
        except Exception as e:
            logger.warning(f"   Direct collection access failed: {e}")
            php_codes = []
        
        if not php_codes:
            logger.warning("⚠️ No PHP code found in codebase - using defaults")
            return self._get_default_php_patterns()
        
        # Combine all PHP code (includes inline HTML/CSS/JS)
        all_php_code = "\n\n".join([code['content'] for code in php_codes])
        logger.info(f"📝 Combined inline PHP code size: {len(all_php_code)} characters")
        logger.info(f"   This includes embedded HTML, CSS, and JavaScript")
        
        # Extract patterns - INCLUDING ALL 12 MISSING PATTERNS
        # Since PHP files contain inline HTML/CSS/JS, we extract ALL patterns from PHP code
        patterns = {
            'functions': self._extract_function_names(all_php_code),
            'table_names': self._extract_table_names(all_php_code),
            'field_names': self._extract_field_names(all_php_code),
            'ajax_functions': self._extract_ajax_functions(all_php_code),
            'db_connection': self._extract_db_connection_pattern(all_php_code),
            'session_management': self._extract_session_pattern(all_php_code),
            'validation_functions': self._extract_validation_functions(all_php_code),
            'transaction_management': self._extract_transaction_pattern(all_php_code),
            'naming_conventions': self._analyze_naming_conventions(all_php_code),
            'common_variables': self._extract_common_variables(all_php_code),
            'response_patterns': self._extract_response_patterns(all_php_code),
            'include_patterns': self._extract_include_patterns(all_php_code),
            # 🆕 12 CRITICAL PATTERNS - EXTRACTED FROM INLINE PHP FILES
            'ajax_auto_id': self._extract_ajax_auto_id_generation(all_php_code),
            'delete_checks': self._extract_delete_dependency_checks(all_php_code),
            'chart_integration': self._extract_chart_of_accounts_integration(all_php_code),
            'conditional_logic': self._extract_conditional_code_generation(all_php_code),
            'dynamic_dropdowns': self._extract_dynamic_dropdown_population(all_php_code),
            'formvalidation': self._extract_formvalidation_framework(all_php_code),
            'keyboard_navigation': self._extract_keyboard_navigation(all_php_code),
            'grid_patterns': self._extract_grid_table_patterns(all_php_code),
            'disabled_fields': self._extract_disabled_field_handling(all_php_code),
            'asset_loading': self._extract_complete_asset_loading(all_php_code),
            'php_includes': self._extract_php_include_files(all_php_code),
            # 🆕 HTML/CSS patterns from inline PHP files
            'css_classes': self._extract_common_css_classes(all_php_code),
            'form_structure': self._extract_form_structure(all_php_code),
            'bootstrap_usage': self._check_bootstrap_usage(all_php_code)
        }
        
        logger.info(f"📊 Unified PHP Patterns Summary:")
        logger.info(f"   - Functions: {len(patterns['functions'])}")
        logger.info(f"   - Tables: {len(patterns['table_names'])}")
        logger.info(f"   - Fields: {len(patterns['field_names'])}")
        logger.info(f"   - AJAX: {len(patterns['ajax_functions'])}")
        logger.info(f"   - CSS Classes: {len(patterns['css_classes'])}")
        
        return patterns
    
    def _analyze_html_patterns_sync(self, codebase_id: str) -> Dict:
        """
        🆕 UNIFIED: Extract HTML patterns from inline PHP files
        Company codebase has HTML embedded in PHP files, not separate HTML files
        """
        logger.info(f"🔍 Starting HTML pattern analysis (SYNC) for codebase: {codebase_id}")
        logger.info(f"   📋 Extracting HTML patterns from inline PHP files")
        
        # Get PHP documents (which contain inline HTML)
        php_codes = []
        try:
            logger.info(f"🔍 Attempting direct collection access for HTML in PHP files...")
            collection = self.embedding_manager.vectorstore._collection
            all_docs = collection.get()
            
            if all_docs and all_docs.get('documents'):
                # Filter for PHP documents (which contain inline HTML)
                for i, doc in enumerate(all_docs['documents']):
                    metadata = all_docs['metadatas'][i] if all_docs.get('metadatas') else {}
                    
                    # Get PHP files from current codebase (they contain inline HTML)
                    if (metadata.get('language') == 'php' and 
                        metadata.get('codebase_id') == codebase_id):
                        php_codes.append({
                            'content': doc,
                            'metadata': metadata
                        })
                
                logger.info(f"🔍 Direct access found {len(php_codes)} PHP documents (with inline HTML)")
        except Exception as e:
            logger.warning(f"   Direct collection access failed: {e}")
            php_codes = []
        
        if not php_codes:
            logger.warning("⚠️ No PHP code found - using defaults")
            return self._get_default_html_patterns()
        
        # Combine all PHP code (which includes inline HTML)
        all_code = "\n\n".join([code['content'] for code in php_codes])
        logger.info(f"📝 Combined code size: {len(all_code)} characters")
        
        # Extract HTML patterns from inline PHP files
        return {
            'form_structure': self._extract_form_structure(all_code),
            'css_classes': self._extract_common_css_classes(all_code),
            'table_structure': self._extract_table_structure(all_code),
            'bootstrap_usage': self._check_bootstrap_usage(all_code),
            # 🆕 12 ESSENTIAL PATTERNS FROM INLINE PHP FILES
            'ajax_auto_id': self._extract_ajax_auto_id_generation(all_code),
            'delete_checks': self._extract_delete_dependency_checks(all_code),
            'chart_integration': self._extract_chart_of_accounts_integration(all_code),
            'conditional_logic': self._extract_conditional_code_generation(all_code),
            'dynamic_dropdowns': self._extract_dynamic_dropdown_population(all_code),
            'formvalidation': self._extract_formvalidation_framework(all_code),
            'keyboard_navigation': self._extract_keyboard_navigation(all_code),
            'grid_patterns': self._extract_grid_table_patterns(all_code),
            'disabled_fields': self._extract_disabled_field_handling(all_code),
            'asset_loading': self._extract_complete_asset_loading(all_code),
            'php_includes': self._extract_php_include_files(all_code)
        }
    
    def _analyze_css_patterns_sync(self, codebase_id: str) -> Dict:
        """
        🆕 UNIFIED: Extract CSS patterns from inline PHP files
        Company codebase has CSS in <style> tags or <link> in PHP files
        """
        logger.info(f"🔍 Starting CSS pattern analysis (SYNC) for codebase: {codebase_id}")
        logger.info(f"   📋 Extracting CSS patterns from inline PHP files + separate CSS files")
        
        # Get both PHP documents (inline CSS) and separate CSS files
        all_codes = []
        try:
            collection = self.embedding_manager.vectorstore._collection
            all_docs = collection.get()
            
            if all_docs and all_docs.get('documents'):
                for i, doc in enumerate(all_docs['documents']):
                    metadata = all_docs['metadatas'][i] if all_docs.get('metadatas') else {}
                    
                    # Get PHP files (inline CSS) + separate CSS files from current codebase
                    if metadata.get('codebase_id') == codebase_id:
                        if metadata.get('language') in ['css', 'php']:
                            all_codes.append({'content': doc, 'metadata': metadata})
                
                logger.info(f"🔍 Direct access found {len(all_codes)} documents with CSS")
        except Exception as e:
            logger.warning(f"   Direct collection access failed: {e}")
            all_codes = []
        
        if not all_codes:
            logger.warning("⚠️ No CSS code found in codebase - using defaults")
            return self._get_default_css_patterns()
        
        all_css = "\n\n".join([code['content'] for code in all_codes])
        
        return {
            'color_scheme': self._extract_color_scheme(all_css),
            'common_classes': self._extract_common_css_classes(all_css),
            'responsive_design': self._check_responsive_design(all_css)
        }
    
    def _analyze_js_patterns_sync(self, codebase_id: str) -> Dict:
        """
        🆕 UNIFIED: Extract JS patterns from inline PHP files
        Company codebase has JavaScript in <script> tags inside PHP files
        """
        logger.info(f"🔍 Starting JS pattern analysis (SYNC) for codebase: {codebase_id}")
        logger.info(f"   📋 Extracting JS patterns from inline PHP files + separate JS files")
        
        # Get both PHP documents (inline JS) and separate JS files
        all_codes = []
        try:
            collection = self.embedding_manager.vectorstore._collection
            all_docs = collection.get()
            
            if all_docs and all_docs.get('documents'):
                for i, doc in enumerate(all_docs['documents']):
                    metadata = all_docs['metadatas'][i] if all_docs.get('metadatas') else {}
                    
                    # Get PHP files (inline JS) + separate JS files from current codebase
                    if metadata.get('codebase_id') == codebase_id:
                        if metadata.get('language') in ['js', 'php']:
                            all_codes.append({'content': doc, 'metadata': metadata})
                
                logger.info(f"🔍 Direct access found {len(all_codes)} documents with JavaScript")
        except Exception as e:
            logger.warning(f"   Direct collection access failed: {e}")
            all_codes = []
        
        if not all_codes:
            logger.warning("⚠️ No JS code found in codebase - using defaults")
            return self._get_default_js_patterns()
        
        all_js = "\n\n".join([code['content'] for code in all_codes])
        
        return {
            'ajax_patterns': self._extract_ajax_functions(all_js),
            'validation_patterns': self._extract_validation_functions(all_js),
            'common_functions': self._extract_function_names(all_js),
            # 🆕 12 ESSENTIAL PATTERNS FROM INLINE PHP FILES
            'ajax_auto_id': self._extract_ajax_auto_id_generation(all_js),
            'delete_checks': self._extract_delete_dependency_checks(all_js),
            'chart_integration': self._extract_chart_of_accounts_integration(all_js),
            'conditional_logic': self._extract_conditional_code_generation(all_js),
            'dynamic_dropdowns': self._extract_dynamic_dropdown_population(all_js),
            'formvalidation': self._extract_formvalidation_framework(all_js),
            'keyboard_navigation': self._extract_keyboard_navigation(all_js),
            'grid_patterns': self._extract_grid_table_patterns(all_js),
            'disabled_fields': self._extract_disabled_field_handling(all_js),
            'asset_loading': self._extract_complete_asset_loading(all_js),
            'php_includes': self._extract_php_include_files(all_js)
        }
    
    def _analyze_sql_patterns_sync(self, codebase_id: str) -> Dict:
        """
        🆕 FIXED: Synchronous SQL pattern analysis
        """
        logger.info(f"🔍 Starting SQL pattern analysis (SYNC) for codebase: {codebase_id}")
        
        # Get SQL documents directly from collection
        sql_codes = []
        try:
            collection = self.embedding_manager.vectorstore._collection
            all_docs = collection.get()
            
            if all_docs and all_docs.get('documents'):
                for i, doc in enumerate(all_docs['documents']):
                    metadata = all_docs['metadatas'][i] if all_docs.get('metadatas') else {}
                    
                    if (
                        metadata.get('language') == 'sql'
                        and metadata.get('codebase_id') == codebase_id
                    ):
                        sql_codes.append({'content': doc, 'metadata': metadata})
                
                logger.info(f"🔍 Direct access found {len(sql_codes)} SQL documents")
        except Exception as e:
            logger.warning(f"   Direct collection access failed: {e}")
            sql_codes = []
        
        if not sql_codes:
            logger.warning("⚠️ No SQL code found in codebase - using defaults")
            return self._get_default_sql_patterns()
        
        all_sql = "\n\n".join([code['content'] for code in sql_codes])
        
        return {
            'table_names': self._extract_table_names(all_sql),
            'column_names': self._extract_field_names(all_sql),
            'db_engine': self._extract_db_engine(all_sql)
        }
    
    def _get_default_php_patterns(self) -> Dict:
        """Default PHP patterns when no code found"""
        return {
            'functions': [],
            'table_names': [],
            'field_names': [],
            'ajax_functions': [],
            'db_connection': None,
            'session_management': None,
            'validation_functions': [],
            'transaction_management': {'start': None, 'end': None},
            'naming_conventions': {},
            'common_variables': [],
            'response_patterns': [],
            'include_patterns': []
        }
    
    def _get_default_html_patterns(self) -> Dict:
        """Default HTML patterns when no code found"""
        return {
            'form_structure': [],
            'css_classes': [],
            'table_structure': [],
            'bootstrap_usage': False
        }
    
    def _get_default_css_patterns(self) -> Dict:
        """Default CSS patterns when no code found"""
        return {
            'color_scheme': [],
            'common_classes': [],
            'responsive_design': False
        }
    
    def _get_default_js_patterns(self) -> Dict:
        """Default JS patterns when no code found"""
        return {
            'ajax_patterns': [],
            'validation_patterns': [],
            'common_functions': []
        }
    
    def _get_default_sql_patterns(self) -> Dict:
        """Default SQL patterns when no code found"""
        return {
            'table_names': [],
            'column_names': [],
            'db_engine': None
        }
    
    def _extract_form_structure(self, code: str) -> List[str]:
        """Extract form structures"""
        form_pattern = r'<form[^>]*>(.*?)</form>'
        matches = re.findall(form_pattern, code, re.IGNORECASE | re.DOTALL)
        return matches[:5]
    
    def _extract_table_structure(self, code: str) -> List[str]:
        """Extract table structures"""
        table_pattern = r'<table[^>]*>(.*?)</table>'
        matches = re.findall(table_pattern, code, re.IGNORECASE | re.DOTALL)
        return matches[:5]
    
    def _check_bootstrap_usage(self, code: str) -> bool:
        """Check if Bootstrap is used"""
        return 'bootstrap' in code.lower() or 'col-md' in code or 'col-lg' in code
    
    def _check_responsive_design(self, code: str) -> bool:
        """Check if responsive design is used"""
        return '@media' in code or 'viewport' in code.lower()
    
    def _extract_color_scheme(self, code: str) -> List[str]:
        """Extract color scheme"""
        color_pattern = r'#[0-9a-fA-F]{6}|rgb\([^)]+\)'
        matches = re.findall(color_pattern, code)
        return list(set(matches))[:10]
    
    def _extract_db_engine(self, code: str) -> str:
        """Extract database engine"""
        if 'InnoDB' in code:
            return 'InnoDB'
        elif 'MyISAM' in code:
            return 'MyISAM'
        return None
    
    async def analyze_codebase_patterns(self, codebase_id: str) -> Dict:
        """
        Analyze entire codebase and extract common patterns
        
        Returns:
            {
                'php': {
                    'functions': ['most_used_function1', 'function2', ...],
                    'db_connection': 'actual connection pattern',
                    'session_management': 'actual session pattern',
                    'validation_functions': [...],
                    'naming_conventions': {...}
                },
                'html': {...},
                'css': {...},
                'js': {...}
            }
        """
        logger.info(f"🔍 Analyzing codebase {codebase_id} for patterns...")
        
        # 🆕 DIAGNOSTIC: Check vectorstore status
        logger.info("🔍 DIAGNOSTIC: Checking vectorstore status...")
        try:
            total_docs = self.embedding_manager.get_vectorstore_stats()
            logger.info(f"   Total documents in vectorstore: {total_docs}")
        except Exception as e:
            logger.error(f"   Error checking vectorstore: {e}")
        
        patterns = {
            'php': await self._analyze_php_patterns(codebase_id),
            'html': await self._analyze_html_patterns(codebase_id),
            'css': await self._analyze_css_patterns(codebase_id),
            'js': await self._analyze_js_patterns(codebase_id),
            'sql': await self._analyze_sql_patterns(codebase_id)
        }
        
        logger.info(f"✅ Pattern analysis complete for {codebase_id}")
        return patterns
    
    async def _analyze_php_patterns(self, codebase_id: str) -> Dict:
        """
        Extract PHP patterns from company codebase
        """
        logger.info(f"🔍 Starting PHP pattern analysis for codebase: {codebase_id}")
        logger.info(f"   User ID: {self.user_id} (type: {type(self.user_id).__name__})")
        logger.info(f"   Codebase ID: {codebase_id} (type: {type(codebase_id).__name__})")
        
        # 🆕 DIAGNOSTIC: Check vectorstore status
        try:
            total_docs = self.embedding_manager.get_vectorstore_stats()
            logger.info(f"   Total documents in vectorstore: {total_docs}")
        except Exception as e:
            logger.error(f"   Error checking vectorstore: {e}")
        
        # 🆕 DIRECT ACCESS: Get PHP documents directly from collection
        php_codes = []
        try:
            logger.info(f"🔍 Attempting direct collection access...")
            collection = self.embedding_manager.vectorstore._collection
            all_docs = collection.get()
            
            if all_docs and all_docs.get('documents'):
                logger.info(f"   Total documents in collection: {len(all_docs['documents'])}")
                
                # Filter for PHP documents
                for i, doc in enumerate(all_docs['documents']):
                    metadata = all_docs['metadatas'][i] if all_docs.get('metadatas') else {}
                    
                    # Check if this is a PHP file
                    if metadata.get('language') == 'php':
                        php_codes.append({
                            'content': doc,
                            'metadata': metadata
                        })
                
                logger.info(f"🔍 Direct access found {len(php_codes)} PHP documents")
                
                # Also log metadata of first PHP doc for debugging
                if php_codes:
                    logger.info(f"   First PHP doc metadata: {php_codes[0]['metadata']}")
        except Exception as e:
            logger.warning(f"   Direct collection access failed: {e}")
            php_codes = []
        
        # If direct access didn't work, try search with filters
        if not php_codes:
            logger.info(f"🔍 Falling back to search with codebase_id filter...")
            php_codes = self.embedding_manager.search_similar_code(
                query="php code functions database",
                k=100,  # Get many samples
                filter_dict={
                    'language': 'php',
                    'user_id': str(self.user_id),  # Ensure string
                    'codebase_id': str(codebase_id)  # Ensure string
                }
            )
            
            logger.info(f"🔍 PHP Code Search (with codebase_id filter): Found {len(php_codes)} PHP files")
            
            # If no results with codebase_id, try without it
            if not php_codes:
                logger.warning(f"⚠️ No PHP files found with codebase_id filter, trying without...")
                php_codes = self.embedding_manager.search_similar_code(
                    query="php code functions database",
                    k=100,
                    filter_dict={
                        'language': 'php',
                        'user_id': str(self.user_id)
                    }
                )
                logger.info(f"🔍 PHP Code Search (without codebase_id): Found {len(php_codes)} PHP files")
            
            # If still no results, try with just language filter
            if not php_codes:
                logger.warning(f"⚠️ No PHP files found with user_id filter, trying with just language...")
                php_codes = self.embedding_manager.search_similar_code(
                    query="php code functions database",
                    k=100,
                    filter_dict={
                        'language': 'php'
                    }
                )
                logger.info(f"🔍 PHP Code Search (language only): Found {len(php_codes)} PHP files")
            
            # If still no results, try without any filter
            if not php_codes:
                logger.warning(f"⚠️ No PHP files found with language filter, trying without any filter...")
                php_codes = self.embedding_manager.search_similar_code(
                    query="php code functions database",
                    k=100,
                    filter_dict=None
                )
                logger.info(f"🔍 PHP Code Search (no filter): Found {len(php_codes)} PHP files")
        
        if not php_codes:
            logger.warning("⚠️ No PHP code found in codebase - using defaults")
            logger.warning(f"⚠️ This means pattern extraction will use DEFAULT patterns, not company-specific patterns!")
            logger.warning(f"⚠️ Check if documents were indexed correctly in vectorstore")
            return self._get_default_php_patterns()
        
        # Combine all PHP code
        all_php_code = "\n\n".join([code['content'] for code in php_codes])
        logger.info(f"📝 Combined PHP code size: {len(all_php_code)} characters")
        logger.info(f"📝 First 500 chars of combined code: {all_php_code[:500]}")
        
        # Extract patterns with detailed logging
        logger.info("🔍 Extracting table names...")
        table_names = self._extract_table_names(all_php_code)
        logger.info(f"✅ Table names extracted: {len(table_names)} - {table_names[:5]}")
        
        logger.info("🔍 Extracting field names...")
        field_names = self._extract_field_names(all_php_code)
        logger.info(f"✅ Field names extracted: {len(field_names)} - {field_names[:5]}")
        
        logger.info("🔍 Extracting AJAX functions...")
        ajax_functions = self._extract_ajax_functions(all_php_code)
        logger.info(f"✅ AJAX functions extracted: {len(ajax_functions)} - {ajax_functions[:5]}")
        
        logger.info("🔍 Extracting function names...")
        function_names = self._extract_function_names(all_php_code)
        logger.info(f"✅ Function names extracted: {len(function_names)} - {function_names[:5]}")
        
        # Extract patterns
        patterns = {
            'functions': function_names,
            'table_names': table_names,
            'field_names': field_names,
            'ajax_functions': ajax_functions,
            'db_connection': self._extract_db_connection_pattern(all_php_code),
            'session_management': self._extract_session_pattern(all_php_code),
            'validation_functions': self._extract_validation_functions(all_php_code),
            'transaction_management': self._extract_transaction_pattern(all_php_code),
            'naming_conventions': self._analyze_naming_conventions(all_php_code),
            'common_variables': self._extract_common_variables(all_php_code),
            'response_patterns': self._extract_response_patterns(all_php_code),
            'include_patterns': self._extract_include_patterns(all_php_code),
            # 🆕 12 ESSENTIAL PATTERNS - NOW EXTRACTED IN ASYNC METHOD TOO
            'ajax_auto_id': self._extract_ajax_auto_id_generation(all_php_code),
            'delete_checks': self._extract_delete_dependency_checks(all_php_code),
            'chart_integration': self._extract_chart_of_accounts_integration(all_php_code),
            'conditional_logic': self._extract_conditional_code_generation(all_php_code),
            'dynamic_dropdowns': self._extract_dynamic_dropdown_population(all_php_code),
            'formvalidation': self._extract_formvalidation_framework(all_php_code),
            'keyboard_navigation': self._extract_keyboard_navigation(all_php_code),
            'grid_patterns': self._extract_grid_table_patterns(all_php_code),
            'disabled_fields': self._extract_disabled_field_handling(all_php_code),
            'asset_loading': self._extract_complete_asset_loading(all_php_code),
            'php_includes': self._extract_php_include_files(all_php_code)
        }
        
        logger.info(f"📊 PHP Patterns Summary:")
        logger.info(f"   - Functions: {len(patterns['functions'])}")
        logger.info(f"   - Tables: {len(patterns['table_names'])}")
        logger.info(f"   - Fields: {len(patterns['field_names'])}")
        logger.info(f"   - AJAX: {len(patterns['ajax_functions'])}")
        logger.info(f"   - DB Connection: {bool(patterns['db_connection'])}")
        logger.info(f"   - Session: {bool(patterns['session_management'])}")
        logger.info(f"   - 🆕 AJAX Auto-ID: {len(patterns['ajax_auto_id'])}")
        logger.info(f"   - 🆕 Delete Checks: {len(patterns['delete_checks'])}")
        logger.info(f"   - 🆕 Chart Integration: {len(patterns['chart_integration'])}")
        logger.info(f"   - 🆕 Dynamic Dropdowns: {len(patterns['dynamic_dropdowns'])}")
        logger.info(f"   - 🆕 Grid Patterns: {len(patterns['grid_patterns'])}")
        logger.info(f"   - 🆕 PHP Includes: {len(patterns['php_includes'])}")
        
        return patterns
    
    def _extract_function_names(self, code: str) -> List[str]:
        """
        Extract all function names and count frequency
        Returns top 20 most used functions
        """
        # Match function calls: functionName(
        function_pattern = r'\b([a-zA-Z_][a-zA-Z0-9_]*)\s*\('
        matches = re.findall(function_pattern, code)
        
        # Count frequency
        function_counts = Counter(matches)
        
        # Filter out common PHP built-ins
        php_builtins = {'echo', 'print', 'isset', 'empty', 'array', 'count', 
                       'strlen', 'substr', 'trim', 'explode', 'implode', 'date',
                       'time', 'strtotime', 'json_encode', 'json_decode'}
        
        # Get custom functions (not built-ins)
        custom_functions = [
            func for func, count in function_counts.most_common(50)
            if func not in php_builtins and count > 2  # Used at least 3 times
        ]
        
        return custom_functions[:20]  # Top 20
    
    def _extract_table_names(self, code: str) -> List[str]:
        """
        Extract database table names from SQL and PHP code
        Looks for: CREATE TABLE, INSERT INTO, SELECT FROM, UPDATE, DELETE FROM, db_insert, db_update, db_delete
        
        🆕 ISSUE #1 FIX: Filter out PHPExcel library classes that contaminate table name extraction
        """
        tables = []
        
        # Pattern 1: SQL CREATE TABLE
        pattern1 = r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?([a-zA-Z_][a-zA-Z0-9_]*)`?'
        matches = re.findall(pattern1, code, re.IGNORECASE)
        tables.extend(matches)
        logger.info(f"  Pattern 1 (CREATE TABLE): {len(matches)} matches - {matches[:3]}")
        
        # Pattern 2: SQL INSERT/UPDATE/DELETE
        pattern2 = r'(?:INSERT|UPDATE|DELETE)\s+(?:INTO\s+)?`?([a-zA-Z_][a-zA-Z0-9_]*)`?'
        matches = re.findall(pattern2, code, re.IGNORECASE)
        tables.extend(matches)
        logger.info(f"  Pattern 2 (INSERT/UPDATE/DELETE): {len(matches)} matches - {matches[:3]}")
        
        # Pattern 3: SQL FROM/JOIN
        pattern3 = r'(?:FROM|JOIN)\s+`?([a-zA-Z_][a-zA-Z0-9_]*)`?'
        matches = re.findall(pattern3, code, re.IGNORECASE)
        tables.extend(matches)
        logger.info(f"  Pattern 3 (FROM/JOIN): {len(matches)} matches - {matches[:3]}")
        
        # Pattern 4: PHP db_insert/db_update/db_delete calls
        pattern4 = r'db_(?:insert|update|delete)\s*\(\s*["\']?([a-zA-Z_][a-zA-Z0-9_]*)["\']?'
        matches = re.findall(pattern4, code, re.IGNORECASE)
        tables.extend(matches)
        logger.info(f"  Pattern 4 (db_* functions): {len(matches)} matches - {matches[:3]}")
        
        # Pattern 5: PHP $table = "tablename" assignments
        pattern5 = r'\$table\s*=\s*["\']([a-zA-Z_][a-zA-Z0-9_]*)["\']'
        matches = re.findall(pattern5, code, re.IGNORECASE)
        tables.extend(matches)
        logger.info(f"  Pattern 5 ($table assignments): {len(matches)} matches - {matches[:3]}")
        
        # Pattern 6: Table names in strings (common pattern) - more specific
        pattern6 = r"(?:tbl|table_)['\"]?([a-zA-Z_][a-zA-Z0-9_]*)['\"]?"
        matches = re.findall(pattern6, code, re.IGNORECASE)
        tables.extend(matches)
        logger.info(f"  Pattern 6 (tbl* prefix): {len(matches)} matches - {matches[:3]}")
        
        # 🆕 ISSUE #1 FIX: Blacklist PHPExcel library classes and common false positives
        # These are NOT database tables - they're library classes that contaminate extraction
        phpexcel_blacklist = {
            # PHPExcel core classes
            'cell', 'pear', 'row', 'column', 'worksheet', 'workbook', 'reader', 'writer',
            'style', 'font', 'border', 'fill', 'alignment', 'protection', 'numberformat',
            'conditional', 'datavalidation', 'comment', 'hyperlink', 'richtext',
            # PHPExcel calculation classes
            'ptgparen', 'ptgmemfuncv', 'ptgmemfunc', 'ptgmemarea', 'ptgmemareav',
            'fontindex', 'formatindex', 'xfindex', 'styleindex',
            # PHPExcel internal classes
            'cell_frame_reflower', 'blanks', 'numbers', 'integer', 'ui4', 'denomination',
            'sra1', 'foo', 'which', 'last', 'rich', 'grid',
            # Common false positives
            'value', 'data', 'result', 'row', 'col', 'item', 'list', 'array',
            'object', 'class', 'interface', 'trait', 'namespace', 'use',
            # SQL keywords
            'select', 'from', 'where', 'and', 'or', 'not', 'in', 'like', 
            'if', 'else', 'function', 'return', 'echo', 'print', 'true', 'false', 'null'
        }
        
        # Filter out blacklisted items and keep only valid table names
        unique_tables = []
        for t in set(tables):
            t_lower = t.lower()
            # Skip if in blacklist
            if t_lower in phpexcel_blacklist:
                continue
            # Skip if too short (< 3 chars)
            if len(t) < 3:
                continue
            # Skip if contains only numbers
            if t.isdigit():
                continue
            # ✅ Valid table name - add to list
            unique_tables.append(t)
        
        # Remove duplicates
        unique_tables = list(set(unique_tables))
        
        logger.info(f"🔍 Table Names Extracted: {len(unique_tables)} unique tables (after PHPExcel filtering)")
        if unique_tables:
            logger.info(f"   Examples: {unique_tables[:10]}")
        
        return unique_tables[:30]  # Top 30 table names
    
    def _extract_field_names(self, code: str) -> List[str]:
        """
        Extract database field/column names from SQL and PHP code
        Looks for: column definitions, field references, POST/GET parameters
        """
        fields = []
        
        # Pattern 1: SQL column definitions (VARCHAR, INT, etc.)
        pattern1 = r'`?([a-zA-Z_][a-zA-Z0-9_]*)`?\s+(?:VARCHAR|INT|TEXT|DATE|DATETIME|DECIMAL|FLOAT|ENUM|TINYINT|BIGINT|BOOLEAN|BLOB)'
        matches = re.findall(pattern1, code, re.IGNORECASE)
        fields.extend(matches)
        logger.info(f"  Pattern 1 (SQL columns): {len(matches)} matches")
        
        # Pattern 2: PHP array keys (key => value)
        pattern2 = r"['\"]([a-zA-Z_][a-zA-Z0-9_]*)['\"](?:\s*=>|\s*:)"
        matches = re.findall(pattern2, code, re.IGNORECASE)
        fields.extend(matches)
        logger.info(f"  Pattern 2 (array keys): {len(matches)} matches")
        
        # Pattern 3: POST field names
        pattern3 = r'\$_POST\s*\[\s*["\']([a-zA-Z_][a-zA-Z0-9_]*)["\']'
        matches = re.findall(pattern3, code, re.IGNORECASE)
        fields.extend(matches)
        logger.info(f"  Pattern 3 ($_POST): {len(matches)} matches")
        
        # Pattern 4: GET field names
        pattern4 = r'\$_GET\s*\[\s*["\']([a-zA-Z_][a-zA-Z0-9_]*)["\']'
        matches = re.findall(pattern4, code, re.IGNORECASE)
        fields.extend(matches)
        logger.info(f"  Pattern 4 ($_GET): {len(matches)} matches")
        
        # Pattern 5: HTML form field names
        pattern5 = r'name\s*=\s*["\']([a-zA-Z_][a-zA-Z0-9_]*)["\']'
        matches = re.findall(pattern5, code, re.IGNORECASE)
        fields.extend(matches)
        logger.info(f"  Pattern 5 (HTML name): {len(matches)} matches")
        
        # Pattern 6: PHP variable assignments ($var = ...)
        pattern6 = r'\$([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(?:add|getvalue|noformat)\s*\('
        matches = re.findall(pattern6, code, re.IGNORECASE)
        fields.extend(matches)
        logger.info(f"  Pattern 6 (PHP variables): {len(matches)} matches")
        
        # Pattern 7: $columns array assignments
        pattern7 = r'\$columns\s*\[\s*["\']([a-zA-Z_][a-zA-Z0-9_]*)["\']'
        matches = re.findall(pattern7, code, re.IGNORECASE)
        fields.extend(matches)
        logger.info(f"  Pattern 7 ($columns): {len(matches)} matches")
        
        # Remove duplicates and common keywords
        keywords = {'if', 'else', 'for', 'while', 'function', 'return', 'echo', 'print', 'array', 'true', 'false', 'null', 'isset', 'empty', 'die', 'exit'}
        unique_fields = list(set([f for f in fields if f.lower() not in keywords and len(f) > 1]))
        
        logger.info(f"🔍 Field Names Extracted: {len(unique_fields)} unique fields - {unique_fields[:15]}")
        
        return unique_fields[:50]  # Top 50 field names
    
    def _extract_ajax_functions(self, code: str) -> List[str]:
        """
        ✅ ISSUE #1 FIX: Enhanced AJAX function extraction with more patterns
        Extract AJAX function names and patterns
        Looks for: $.ajax, $.post, $.get, fetch calls, and AJAX endpoint names
        """
        ajax_funcs = []
        
        # Pattern 1: AJAX URLs (url: "endpoint.php")
        pattern1 = r'url\s*:\s*["\']([a-zA-Z_][a-zA-Z0-9_\.]*\.php)["\']'
        matches = re.findall(pattern1, code, re.IGNORECASE)
        ajax_funcs.extend(matches)
        logger.info(f"  Pattern 1 (AJAX URLs): {len(matches)} matches")
        
        # Pattern 2: AJAX endpoint names (url: "GetMaxID", url: "SaveCustomer")
        pattern2 = r'url\s*:\s*["\']([a-zA-Z_][a-zA-Z0-9_]*)["\']'
        matches = re.findall(pattern2, code, re.IGNORECASE)
        ajax_funcs.extend(matches)
        logger.info(f"  Pattern 2 (AJAX endpoints): {len(matches)} matches")
        
        # Pattern 3: $.post/$.get/$.ajax calls
        pattern3 = r'\$\.(?:post|get|ajax)\s*\(\s*["\']([a-zA-Z_][a-zA-Z0-9_\.]*)["\']'
        matches = re.findall(pattern3, code, re.IGNORECASE)
        ajax_funcs.extend(matches)
        logger.info(f"  Pattern 3 ($.post/$.get): {len(matches)} matches")
        
        # Pattern 4: fetch() calls
        pattern4 = r'fetch\s*\(\s*["\']([a-zA-Z_][a-zA-Z0-9_\.]*)["\']'
        matches = re.findall(pattern4, code, re.IGNORECASE)
        ajax_funcs.extend(matches)
        logger.info(f"  Pattern 4 (fetch): {len(matches)} matches")
        
        # Pattern 5: PHP action parameters ($_REQUEST['action'] == 'GetMaxID')
        pattern5 = r"['\"]([a-zA-Z_][a-zA-Z0-9_]*)['\"](?:\s*==|\s*===)"
        matches = re.findall(pattern5, code, re.IGNORECASE)
        ajax_funcs.extend(matches)
        logger.info(f"  Pattern 5 (action params): {len(matches)} matches")
        
        # Pattern 6: Function names with AJAX pattern
        pattern6 = r'function\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\([^)]*\)\s*\{[^}]*(?:\$\.ajax|\$\.post|fetch)'
        matches = re.findall(pattern6, code, re.IGNORECASE | re.DOTALL)
        ajax_funcs.extend(matches)
        logger.info(f"  Pattern 6 (AJAX functions): {len(matches)} matches")
        
        # ✅ ISSUE #1 FIX: Pattern 7 - $.post with inline URL (company pattern)
        # Example: $.post("frmSubArea.php", {Action:'GetMaxID', ...})
        pattern7 = r'\$\.post\s*\(\s*["\']([^"\']+\.php)["\']'
        matches = re.findall(pattern7, code, re.IGNORECASE)
        ajax_funcs.extend(matches)
        logger.info(f"  Pattern 7 ($.post inline): {len(matches)} matches")
        
        # ✅ ISSUE #1 FIX: Pattern 8 - Action parameter values
        # Example: {Action:'GetMaxID', SelectArea: SelectArea}
        pattern8 = r'Action\s*:\s*["\']([a-zA-Z_][a-zA-Z0-9_]*)["\']'
        matches = re.findall(pattern8, code, re.IGNORECASE)
        ajax_funcs.extend(matches)
        logger.info(f"  Pattern 8 (Action values): {len(matches)} matches")
        
        # ✅ ISSUE #1 FIX: Pattern 9 - PHP AJAX handlers
        # Example: if($_REQUEST['Action']=='GetMaxID')
        pattern9 = r"if\s*\(\s*\$_REQUEST\s*\[\s*['\"]Action['\"]\s*\]\s*==\s*['\"]([a-zA-Z_][a-zA-Z0-9_]*)['\"]"
        matches = re.findall(pattern9, code, re.IGNORECASE)
        ajax_funcs.extend(matches)
        logger.info(f"  Pattern 9 (PHP AJAX handlers): {len(matches)} matches")
        
        # ✅ ISSUE #1 FIX: Pattern 10 - AJAX callback functions
        # Example: function(data){ ... }
        pattern10 = r'function\s*\(\s*data\s*\)\s*\{'
        if re.search(pattern10, code, re.IGNORECASE):
            ajax_funcs.append('ajax_callback')
            logger.info(f"  Pattern 10 (AJAX callbacks): Found")
        
        # Remove duplicates and common keywords
        keywords = {'if', 'else', 'for', 'while', 'function', 'return', 'echo', 'print', 'array', 'true', 'false', 'null', 'data', 'success', 'error', 'type', 'method', 'action', 'post', 'get'}
        unique_ajax = list(set([a for a in ajax_funcs if a.lower() not in keywords and len(a) > 2]))
        
        logger.info(f"🔍 AJAX Functions Extracted: {len(unique_ajax)} unique functions - {unique_ajax[:15]}")
        
        return unique_ajax[:30]  # ✅ ISSUE #1 FIX: Increased from 20 to 30 for more coverage
    
    def _extract_db_connection_pattern(self, code: str) -> str:
        """
        Extract actual database connection pattern used in company code
        """
        # Look for mysqli_connect, PDO, or custom connection functions
        patterns = [
            r'mysqli_connect\([^)]+\)',
            r'new\s+mysqli\([^)]+\)',
            r'new\s+PDO\([^)]+\)',
            r'(db_connect|dbConnection|connect_db|getConnection)\s*\([^)]*\)'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, code, re.IGNORECASE)
            if matches:
                # Return most common pattern
                return Counter(matches).most_common(1)[0][0]
        
        return "mysqli_connect('localhost', 'user', 'password', 'database')"
    
    def _extract_session_pattern(self, code: str) -> str:
        """
        Extract session management pattern
        """
        # Look for session start patterns
        patterns = [
            r'session_start\(\)',
            r'(funsession|checkSession|startSession)\s*\([^)]*\)'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, code, re.IGNORECASE)
            if matches:
                return matches[0] if isinstance(matches[0], str) else matches[0][0]
        
        return "session_start()"
    
    def _extract_validation_functions(self, code: str) -> List[str]:
        """
        Extract validation function names
        """
        # Look for functions with 'valid', 'check', 'validate' in name
        validation_pattern = r'\b(valid[a-zA-Z0-9_]*|check[a-zA-Z0-9_]*|validate[a-zA-Z0-9_]*)\s*\('
        matches = re.findall(validation_pattern, code, re.IGNORECASE)
        
        # Get unique validation functions
        validation_funcs = list(set(matches))
        
        return validation_funcs[:10]  # Top 10
    
    def _extract_transaction_pattern(self, code: str) -> Dict:
        """
        Extract transaction management patterns
        """
        start_patterns = re.findall(
            r'(funStartTran|begin_transaction|start_transaction|mysqli_begin_transaction)\s*\([^)]*\)',
            code, re.IGNORECASE
        )
        
        end_patterns = re.findall(
            r'(funEndTran|commit|mysqli_commit)\s*\([^)]*\)',
            code, re.IGNORECASE
        )
        
        return {
            'start': start_patterns[0] if start_patterns else None,
            'end': end_patterns[0] if end_patterns else None
        }
    
    def _analyze_naming_conventions(self, code: str) -> Dict:
        """
        Analyze variable and field naming conventions
        """
        # Extract variable names
        var_pattern = r'\$([a-zA-Z_][a-zA-Z0-9_]*)'
        variables = re.findall(var_pattern, code)
        
        # Analyze patterns
        uppercase_count = sum(1 for v in variables if v.isupper())
        lowercase_count = sum(1 for v in variables if v.islower())
        camelcase_count = sum(1 for v in variables if v[0].islower() and any(c.isupper() for c in v))
        snake_case_count = sum(1 for v in variables if '_' in v)
        
        total = len(variables)
        
        return {
            'uppercase_percent': (uppercase_count / total * 100) if total > 0 else 0,
            'lowercase_percent': (lowercase_count / total * 100) if total > 0 else 0,
            'camelcase_percent': (camelcase_count / total * 100) if total > 0 else 0,
            'snake_case_percent': (snake_case_count / total * 100) if total > 0 else 0,
            'dominant_style': max(
                [('UPPERCASE', uppercase_count), 
                 ('lowercase', lowercase_count),
                 ('camelCase', camelcase_count),
                 ('snake_case', snake_case_count)],
                key=lambda x: x[1]
            )[0]
        }
    
    def _extract_common_variables(self, code: str) -> List[str]:
        """
        Extract most commonly used variable names
        """
        var_pattern = r'\$([a-zA-Z_][a-zA-Z0-9_]*)'
        variables = re.findall(var_pattern, code)
        
        # Count frequency
        var_counts = Counter(variables)
        
        # Filter out super common ones
        common_vars = {'i', 'j', 'k', 'x', 'y', 'result', 'data', 'value'}
        
        custom_vars = [
            var for var, count in var_counts.most_common(30)
            if var not in common_vars
        ]
        
        return custom_vars[:15]
    
    def _extract_response_patterns(self, code: str) -> List[str]:
        """
        Extract response/output patterns
        """
        patterns = [
            r'print\s+"<script>.*?</script>"',
            r'echo\s+"<script>.*?</script>"',
            r'header\([^)]+\)',
            r'json_encode\([^)]+\)',
            r'exit\([^)]*\)'
        ]
        
        found_patterns = []
        for pattern in patterns:
            matches = re.findall(pattern, code, re.DOTALL)
            if matches:
                found_patterns.extend(matches[:2])  # Max 2 examples per type
        
        return found_patterns
    
    def _extract_include_patterns(self, code: str) -> List[str]:
        """
        Extract include/require patterns
        """
        include_pattern = r'(include|require|include_once|require_once)\s*[(\'"](.*?)[\'")]'
        matches = re.findall(include_pattern, code)
        
        # Get unique includes
        includes = list(set([match[1] for match in matches]))
        
        return includes[:10]
    
    def _extract_ajax_auto_id_generation(self, code: str) -> List[Dict]:
        """
        🆕 MISSING PATTERN #1: Extract AJAX Auto-ID Generation patterns
        Example: if($_REQUEST['Action']=='GetMaxID') { echo getMaxID(); exit; }
        """
        ajax_id_patterns = []
        
        # Pattern 1: GetMaxID AJAX handler
        pattern1 = r"if\s*\(\s*\$_REQUEST\s*\[\s*['\"]Action['\"]\s*\]\s*==\s*['\"]GetMaxID['\"]\s*\)\s*\{([^}]+)\}"
        matches = re.findall(pattern1, code, re.IGNORECASE | re.DOTALL)
        for match in matches:
            ajax_id_patterns.append({
                'type': 'GetMaxID',
                'code': match.strip()
            })
        
        # Pattern 2: JavaScript maxid() function
        pattern2 = r"function\s+maxid\s*\(\s*\)\s*\{([^}]+)\}"
        matches = re.findall(pattern2, code, re.IGNORECASE | re.DOTALL)
        for match in matches:
            ajax_id_patterns.append({
                'type': 'maxid_js',
                'code': match.strip()
            })
        
        # Pattern 3: Auto-increment code generation
        pattern3 = r"getvalue\s*\(\s*['\"]SELECT\s+.*?MAX\s*\(.*?\).*?['\"]\s*\)"
        matches = re.findall(pattern3, code, re.IGNORECASE | re.DOTALL)
        for match in matches[:3]:
            ajax_id_patterns.append({
                'type': 'max_query',
                'code': match.strip()
            })
        
        logger.info(f"🔍 AJAX Auto-ID patterns extracted: {len(ajax_id_patterns)}")
        return ajax_id_patterns
    
    def _extract_delete_dependency_checks(self, code: str) -> List[Dict]:
        """
        🆕 MISSING PATTERN #2: Extract relationship validation before delete
        Example: if(getrows2("invoice",$filter)>=1) { alert('Exists in invoice'); exit; }
        """
        delete_checks = []
        
        # Pattern 1: getrows2() dependency check
        pattern1 = r"if\s*\(\s*getrows2\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*\$filter\s*\)\s*>=\s*1\s*\)\s*\{([^}]+)\}"
        matches = re.findall(pattern1, code, re.IGNORECASE | re.DOTALL)
        for table, alert_code in matches:
            delete_checks.append({
                'related_table': table,
                'check_code': f"if(getrows2('{table}',$filter)>=1) {{{alert_code}}}",
                'type': 'dependency_check'
            })
        
        # Pattern 2: Existence check before delete
        pattern2 = r"if\s*\(\s*getrows\s*\(\s*['\"]([^'\"]+)['\"]\s*,[^)]+\)\s*>=\s*1\s*\)"
        matches = re.findall(pattern2, code, re.IGNORECASE)
        for table in matches:
            delete_checks.append({
                'related_table': table,
                'type': 'existence_check'
            })
        
        logger.info(f"🔍 Delete dependency checks extracted: {len(delete_checks)}")
        return delete_checks
    
    def _extract_chart_of_accounts_integration(self, code: str) -> List[Dict]:
        """
        🆕 MISSING PATTERN #3: Extract Chart of Accounts integration
        Example: $don = ACC_CUST.CustomerCode($_REQUEST['CUST_Id']);
                 INSERT INTO chart (ACC_CODE,ACC_NAME,GRP_DET,LEVEL)
        """
        chart_patterns = []
        
        # Pattern 1: ACC_CODE generation
        pattern1 = r"\$\w+\s*=\s*(ACC_\w+)\s*\.\s*(\w+)\s*\([^)]+\)"
        matches = re.findall(pattern1, code, re.IGNORECASE)
        for prefix, func in matches:
            chart_patterns.append({
                'type': 'acc_code_generation',
                'prefix': prefix,
                'function': func
            })
        
        # Pattern 2: Chart INSERT
        pattern2 = r"INSERT\s+INTO\s+chart\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)"
        matches = re.findall(pattern2, code, re.IGNORECASE | re.DOTALL)
        for columns, values in matches:
            chart_patterns.append({
                'type': 'chart_insert',
                'columns': columns.strip(),
                'values': values.strip()
            })
        
        # Pattern 3: Chart UPDATE
        pattern3 = r"UPDATE\s+chart\s+SET\s+([^W]+)\s+WHERE\s+ACC_CODE\s*=\s*['\"]([^'\"]+)['\"]"
        matches = re.findall(pattern3, code, re.IGNORECASE | re.DOTALL)
        for set_clause, acc_code in matches:
            chart_patterns.append({
                'type': 'chart_update',
                'set_clause': set_clause.strip()
            })
        
        # Pattern 4: Chart DELETE
        pattern4 = r"delete\s+from\s+chart\s+where\s+ACC_CODE\s*=\s*['\"]([^'\"]+)['\"]"
        matches = re.findall(pattern4, code, re.IGNORECASE)
        for acc_code in matches:
            chart_patterns.append({
                'type': 'chart_delete',
                'acc_code': acc_code
            })
        
        logger.info(f"🔍 Chart of Accounts patterns extracted: {len(chart_patterns)}")
        return chart_patterns
    
    def _extract_conditional_code_generation(self, code: str) -> Dict:
        """
        🆕 MISSING PATTERN #4: Extract Update vs Insert conditional logic
        Example: if(getrows($table," Code",$value) == '1') { db_update() } else { db_insert() }
        """
        conditional_patterns = {
            'update_check': [],
            'insert_logic': [],
            'update_logic': []
        }
        
        # Pattern 1: Complete if-else block
        pattern1 = r"if\s*\(\s*getrows\s*\([^)]+\)\s*==\s*['\"]?1['\"]?\s*\)\s*\{([^}]+)\}\s*else\s*\{([^}]+)\}"
        matches = re.findall(pattern1, code, re.IGNORECASE | re.DOTALL)
        for update_code, insert_code in matches:
            conditional_patterns['update_logic'].append(update_code.strip())
            conditional_patterns['insert_logic'].append(insert_code.strip())
        
        # Pattern 2: Update check pattern
        pattern2 = r"if\s*\(\s*getrows\s*\(\s*\$table\s*,\s*['\"]([^'\"]+)['\"]\s*,\s*\$(\w+)\s*\)\s*==\s*['\"]?1['\"]?\s*\)"
        matches = re.findall(pattern2, code, re.IGNORECASE)
        for field, var in matches:
            conditional_patterns['update_check'].append({
                'field': field,
                'variable': var
            })
        
        logger.info(f"🔍 Conditional code patterns extracted: {len(conditional_patterns['update_check'])} checks")
        return conditional_patterns
    
    def _extract_dynamic_dropdown_population(self, code: str) -> List[Dict]:
        """
        🆕 MISSING PATTERN #5: Extract dynamic dropdown/cascade patterns
        Example: function SubArea() { $.ajax({ url: form.php, data: { bnkId: $('#Main_Area').val() } }) }
        """
        dropdown_patterns = []
        
        # Pattern 1: AJAX dropdown function
        pattern1 = r"function\s+(\w+)\s*\(\s*\)\s*\{[^}]*\$\.ajax\s*\(\s*\{([^}]+)\}\s*\)"
        matches = re.findall(pattern1, code, re.IGNORECASE | re.DOTALL)
        for func_name, ajax_config in matches:
            dropdown_patterns.append({
                'type': 'ajax_dropdown',
                'function': func_name,
                'config': ajax_config.strip()
            })
        
        # Pattern 2: PHP AJAX handler for dropdown
        pattern2 = r"if\s*\(\s*\$_REQUEST\s*\[\s*['\"](\w+)['\"]\s*\]\s*\)\s*\{[^}]*json_encode[^}]+\}"
        matches = re.findall(pattern2, code, re.IGNORECASE | re.DOTALL)
        for param_name in matches:
            dropdown_patterns.append({
                'type': 'php_dropdown_handler',
                'parameter': param_name
            })
        
        # Pattern 3: onChange event binding
        pattern3 = r"onChange\s*=\s*['\"]([^'\"]+)\(\)['\"]"
        matches = re.findall(pattern3, code, re.IGNORECASE)
        for func in matches:
            dropdown_patterns.append({
                'type': 'onchange_binding',
                'function': func
            })
        
        # ✅ ISSUE #5 FIX: Pattern 4 - onChange with inline condition
        # Example: onChange="if(this.value!='-1'){maxid();}"
        pattern4 = r"onChange\s*=\s*['\"]if\s*\([^)]+\)\s*\{([^}]+)\}['\"]"
        matches = re.findall(pattern4, code, re.IGNORECASE)
        for inline_code in matches:
            dropdown_patterns.append({
                'type': 'onchange_inline',
                'code': inline_code.strip()
            })
        
        # ✅ ISSUE #5 FIX: Pattern 5 - $.post dropdown function (company pattern)
        # Example: function maxid() { $.post("file.php", {Action:'GetMaxID'}) }
        pattern5 = r"function\s+(\w+)\s*\(\s*\)\s*\{[^}]*\$\.post\s*\([^)]+\)"
        matches = re.findall(pattern5, code, re.IGNORECASE | re.DOTALL)
        for func_name in matches:
            dropdown_patterns.append({
                'type': 'post_dropdown',
                'function': func_name
            })
        
        # ✅ ISSUE #5 FIX: Pattern 6 - Parent-child dropdown relationship
        # Example: <select id="cboCountry"> ... <select id="cboArea">
        pattern6 = r"<select[^>]*id\s*=\s*['\"]cbo(\w+)['\"][^>]*>"
        matches = re.findall(pattern6, code, re.IGNORECASE)
        if len(matches) >= 2:  # At least 2 dropdowns = potential cascade
            dropdown_patterns.append({
                'type': 'parent_child_dropdowns',
                'dropdowns': matches
            })
        
        logger.info(f"🔍 Dynamic dropdown patterns extracted: {len(dropdown_patterns)}")
        return dropdown_patterns
    
    def _extract_formvalidation_framework(self, code: str) -> Dict:
        """
        ✅ ISSUE #2 FIX: Enhanced FormValidation.js framework extraction
        Example: $('#frm').formValidation({ framework: "bootstrap", fields: {...} })
        """
        formvalidation_config = {
            'initialization': None,
            'fields': [],
            'validators': [],
            'callbacks': [],
            'has_formvalidation': False,
            'form_selector': None,
            'framework': None
        }
        
        # ✅ ISSUE #2 FIX: Pattern 1 - FormValidation initialization (more flexible)
        # Matches: $('#frm').formValidation({ ... })
        # Matches: $('#frmSaleItem').formValidation({ ... })
        pattern1 = r"\$\s*\(\s*['\"]#(\w+)['\"]\s*\)\s*\.formValidation\s*\(\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}\s*\)"
        matches = re.findall(pattern1, code, re.IGNORECASE | re.DOTALL)
        if matches:
            formvalidation_config['has_formvalidation'] = True
            formvalidation_config['form_selector'] = matches[0][0]
            formvalidation_config['initialization'] = matches[0][1].strip()
            
            # Extract framework
            framework_match = re.search(r'framework\s*:\s*["\'](\w+)["\']', matches[0][1])
            if framework_match:
                formvalidation_config['framework'] = framework_match.group(1)
        
        # ✅ ISSUE #2 FIX: Pattern 2 - Field validation rules (enhanced)
        # Matches: fieldName: { row: '.col-md-4', validators: { notEmpty: {...}, regexp: {...} } }
        pattern2 = r"(\w+)\s*:\s*\{[^}]*validators\s*:\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}"
        matches = re.findall(pattern2, code, re.IGNORECASE | re.DOTALL)
        for field, validators in matches:
            # Skip common keywords
            if field.lower() not in ['button', 'icon', 'framework', 'fields']:
                formvalidation_config['fields'].append({
                    'field': field,
                    'validators': validators.strip()
                })
        
        # ✅ ISSUE #2 FIX: Pattern 3 - Validator types (notEmpty, regexp, emailAddress, etc.)
        validator_types = ['notEmpty', 'regexp', 'emailAddress', 'stringLength', 'numeric', 'callback']
        for validator_type in validator_types:
            pattern = rf"{validator_type}\s*:\s*\{{([^}}]+)\}}"
            matches = re.findall(pattern, code, re.IGNORECASE)
            if matches:
                formvalidation_config['validators'].append({
                    'type': validator_type,
                    'count': len(matches)
                })
        
        # ✅ ISSUE #2 FIX: Pattern 4 - Custom callbacks (enhanced)
        pattern4 = r"callback\s*:\s*\{[^}]*callback\s*:\s*function\s*\([^)]+\)\s*\{([^}]+)\}"
        matches = re.findall(pattern4, code, re.IGNORECASE | re.DOTALL)
        for callback_code in matches:
            formvalidation_config['callbacks'].append(callback_code.strip())
        
        # ✅ ISSUE #2 FIX: Pattern 5 - FormValidation events
        # .on('success.form.fv', function(e) { ... })
        pattern5 = r"\.on\s*\(\s*['\"]success\.form\.fv['\"]\s*,\s*function"
        if re.search(pattern5, code, re.IGNORECASE):
            formvalidation_config['has_success_event'] = True
        
        # ✅ ISSUE #2 FIX: Pattern 6 - FormValidation methods
        # .formValidation('revalidateField', 'fieldName')
        pattern6 = r"\.formValidation\s*\(\s*['\"](\w+)['\"]\s*,"
        methods = re.findall(pattern6, code, re.IGNORECASE)
        if methods:
            formvalidation_config['methods_used'] = list(set(methods))
        
        # ✅ ISSUE #2 FIX: Pattern 7 - Button configuration
        pattern7 = r"button\s*:\s*\{[^}]*selector\s*:\s*['\"]([^'\"]+)['\"]\s*,\s*disabled\s*:\s*['\"]disabled['\"]\s*\}"
        button_match = re.search(pattern7, code, re.IGNORECASE)
        if button_match:
            formvalidation_config['button_selector'] = button_match.group(1)
        
        logger.info(f"🔍 FormValidation config extracted: {len(formvalidation_config['fields'])} fields, Has FV: {formvalidation_config['has_formvalidation']}")
        
        return formvalidation_config
    
    def _extract_keyboard_navigation(self, code: str) -> Dict:
        """
        🆕 MISSING PATTERN #7: Extract keyboard navigation (Enter key) logic
        Example: document.onkeydown = checkKeycode; if(keycode == 13 && field == 'txtName') { nextField.focus(); }
        """
        keyboard_nav = {
            'checkKeycode_function': None,
            'field_mappings': [],
            'complete_code': None
        }
        
        # Pattern 1: Complete checkKeycode function
        pattern1 = r"document\.onkeydown\s*=\s*checkKeycode\s*function\s+checkKeycode\s*\([^)]+\)\s*\{([^}]+)\}"
        matches = re.findall(pattern1, code, re.IGNORECASE | re.DOTALL)
        if matches:
            keyboard_nav['complete_code'] = matches[0].strip()
        
        # Pattern 2: Individual field navigation mappings
        pattern2 = r"if\s*\(\s*keycode\s*==\s*13\s*&&\s*field\s*==\s*['\"](\w+)['\"]\s*\)\s*\{[^}]*getElementById\s*\(\s*['\"](\w+)['\"]\s*\)\.focus\(\)"
        matches = re.findall(pattern2, code, re.IGNORECASE)
        for current_field, next_field in matches:
            keyboard_nav['field_mappings'].append({
                'from': current_field,
                'to': next_field
            })
        
        # Pattern 3: onKeyDown attribute in HTML
        pattern3 = r"onKeyDown\s*=\s*['\"]checkKeycode\s*\(\s*event\s*,\s*this\.id\s*\)['\"]"
        if re.search(pattern3, code, re.IGNORECASE):
            keyboard_nav['has_onkeydown_attribute'] = True
        
        logger.info(f"🔍 Keyboard navigation extracted: {len(keyboard_nav['field_mappings'])} field mappings")
        return keyboard_nav
    
    def _extract_grid_table_patterns(self, code: str) -> List[Dict]:
        """
        🆕 MISSING PATTERN #8: Extract grid/table for detail records
        Example: <table><tr><td><input name="txtField<?php echo $i;?>"></td></tr></table>
        """
        grid_patterns = []
        
        # Pattern 1: PHP loop with indexed inputs
        pattern1 = r"for\s*\(\s*\$i\s*=\s*0\s*;\s*\$i\s*<=\s*\$_REQUEST\s*\[\s*['\"](\w+)['\"]\s*\]\s*;\s*\$i\+\+\s*\)"
        matches = re.findall(pattern1, code, re.IGNORECASE)
        for counter_var in matches:
            grid_patterns.append({
                'type': 'php_loop',
                'counter': counter_var
            })
        
        # Pattern 2: Indexed input fields
        pattern2 = r"name\s*=\s*['\"](\w+)<\?php\s+echo\s+\$(\w+);\s*\?>['\"]"
        matches = re.findall(pattern2, code, re.IGNORECASE)
        for field_name, index_var in matches:
            grid_patterns.append({
                'type': 'indexed_input',
                'field': field_name,
                'index': index_var
            })
        
        # Pattern 3: Grid table structure
        pattern3 = r"<table[^>]*class\s*=\s*['\"]([^'\"]*table[^'\"]*)['\"][^>]*>.*?</table>"
        matches = re.findall(pattern3, code, re.IGNORECASE | re.DOTALL)
        for table_class in matches[:3]:
            grid_patterns.append({
                'type': 'table_structure',
                'class': table_class
            })
        
        # Pattern 4: Checkbox in grid
        pattern4 = r"<input\s+type\s*=\s*['\"]checkbox['\"]\s+name\s*=\s*['\"](\w+)<\?php\s+echo\s+\$\w+;\s*\?>['\"]"
        matches = re.findall(pattern4, code, re.IGNORECASE)
        for checkbox_name in matches:
            grid_patterns.append({
                'type': 'grid_checkbox',
                'name': checkbox_name
            })
        
        logger.info(f"🔍 Grid/table patterns extracted: {len(grid_patterns)}")
        return grid_patterns
    
    def _extract_disabled_field_handling(self, code: str) -> List[Dict]:
        """
        🆕 MISSING PATTERN #10: Extract disabled field handling
        Example: document.getElementById('Main_Area').disabled=false; before submit
        """
        disabled_patterns = []
        
        # Pattern 1: Enable field before submit
        pattern1 = r"document\.getElementById\s*\(\s*['\"](\w+)['\"]\s*\)\.disabled\s*=\s*false"
        matches = re.findall(pattern1, code, re.IGNORECASE)
        for field_id in matches:
            disabled_patterns.append({
                'type': 'enable_before_submit',
                'field': field_id
            })
        
        # Pattern 2: Disabled attribute in HTML
        pattern2 = r"<(?:input|select)[^>]*id\s*=\s*['\"](\w+)['\"][^>]*disabled"
        matches = re.findall(pattern2, code, re.IGNORECASE)
        for field_id in matches:
            disabled_patterns.append({
                'type': 'html_disabled',
                'field': field_id
            })
        
        # Pattern 3: Conditional disable in PHP
        pattern3 = r"<\?php\s+if\s*\([^)]+\)\s*\{\s*echo\s+['\"]disabled['\"]"
        if re.search(pattern3, code, re.IGNORECASE):
            disabled_patterns.append({
                'type': 'conditional_disable',
                'found': True
            })
        
        logger.info(f"🔍 Disabled field patterns extracted: {len(disabled_patterns)}")
        return disabled_patterns
    
    def _extract_complete_asset_loading(self, code: str) -> Dict:
        """
        🆕 MISSING PATTERN #11: Extract complete asset loading (CSS/JS)
        Example: All <link> and <script> tags from company code
        """
        assets = {
            'css_files': [],
            'js_files': [],
            'plugins': [],
            'cdn_links': []
        }
        
        # Pattern 1: CSS files
        pattern1 = r"<link[^>]*href\s*=\s*['\"]([^'\"]+\.css)['\"]"
        matches = re.findall(pattern1, code, re.IGNORECASE)
        assets['css_files'] = list(set(matches))
        
        # Pattern 2: JS files
        pattern2 = r"<script[^>]*src\s*=\s*['\"]([^'\"]+\.js)['\"]"
        matches = re.findall(pattern2, code, re.IGNORECASE)
        assets['js_files'] = list(set(matches))
        
        # Pattern 3: Plugin names
        pattern3 = r"data-plugin\s*=\s*['\"]([^'\"]+)['\"]"
        matches = re.findall(pattern3, code, re.IGNORECASE)
        assets['plugins'] = list(set(matches))
        
        # Pattern 4: CDN links
        pattern4 = r"(?:href|src)\s*=\s*['\"]https?://[^'\"]+['\"]"
        matches = re.findall(pattern4, code, re.IGNORECASE)
        assets['cdn_links'] = list(set(matches))[:10]
        
        logger.info(f"🔍 Asset loading extracted: {len(assets['css_files'])} CSS, {len(assets['js_files'])} JS")
        return assets
    
    def _extract_php_include_files(self, code: str) -> List[Dict]:
        """
        🆕 MISSING PATTERN #12: Extract PHP include files and their purposes
        Example: include("include/config.inc.php"); include("include/topmenu.php");
        """
        includes = []
        
        # Pattern 1: Include statements with paths
        pattern1 = r"(?:include|require|include_once|require_once)\s*\(\s*['\"]([^'\"]+)['\"]"
        matches = re.findall(pattern1, code, re.IGNORECASE)
        for path in matches:
            includes.append({
                'path': path,
                'type': 'config' if 'config' in path.lower() else
                        'menu' if 'menu' in path.lower() else
                        'header' if 'header' in path.lower() else
                        'footer' if 'footer' in path.lower() else
                        'sidebar' if 'sidebar' in path.lower() else 'other'
            })
        
        # Pattern 2: PHP template includes
        pattern2 = r"<\?php\s+include\s*\(\s*['\"]([^'\"]+)['\"]"
        matches = re.findall(pattern2, code, re.IGNORECASE)
        for path in matches:
            if path not in [inc['path'] for inc in includes]:
                includes.append({
                    'path': path,
                    'type': 'template'
                })
        
        logger.info(f"🔍 PHP includes extracted: {len(includes)}")
        return includes
    
    async def _analyze_html_patterns(self, codebase_id: str) -> Dict:
        """
        Extract HTML patterns from company codebase
        """
        logger.info(f"🔍 Starting HTML pattern analysis for codebase: {codebase_id}")
        logger.info(f"   User ID: {self.user_id} (type: {type(self.user_id).__name__})")
        
        # 🆕 DIRECT ACCESS: Get HTML documents directly from collection
        html_codes = []
        try:
            logger.info(f"🔍 Attempting direct collection access for HTML...")
            collection = self.embedding_manager.vectorstore._collection
            all_docs = collection.get()
            
            if all_docs and all_docs.get('documents'):
                # Filter for HTML documents
                for i, doc in enumerate(all_docs['documents']):
                    metadata = all_docs['metadatas'][i] if all_docs.get('metadatas') else {}
                    
                    # Check if this is an HTML file
                    if metadata.get('language') == 'html':
                        html_codes.append({
                            'content': doc,
                            'metadata': metadata
                        })
                
                logger.info(f"🔍 Direct access found {len(html_codes)} HTML documents")
        except Exception as e:
            logger.warning(f"   Direct collection access failed: {e}")
            html_codes = []
        
        # If direct access didn't work, try search with filters
        if not html_codes:
            logger.info(f"🔍 Falling back to search with codebase_id filter...")
            html_codes = self.embedding_manager.search_similar_code(
                query="html form input class style",
                k=100,  # Increased from 50 to 100
                filter_dict={
                    'language': 'html',
                    'user_id': str(self.user_id),  # Ensure string
                    'codebase_id': str(codebase_id)  # Ensure string
                }
            )
            
            logger.info(f"🔍 HTML Code Search (with codebase_id filter): Found {len(html_codes)} HTML files")
            
            # If no results with codebase_id, try without it
            if not html_codes:
                logger.warning(f"⚠️ No HTML files found with codebase_id filter, trying without...")
                html_codes = self.embedding_manager.search_similar_code(
                    query="html form input class style",
                    k=100,
                    filter_dict={
                        'language': 'html',
                        'user_id': str(self.user_id)
                    }
                )
                logger.info(f"🔍 HTML Code Search (without codebase_id): Found {len(html_codes)} HTML files")
            
            # If still no results, try with just language filter
            if not html_codes:
                logger.warning(f"⚠️ No HTML files found with user_id filter, trying with just language...")
                html_codes = self.embedding_manager.search_similar_code(
                    query="html form input class style",
                    k=100,
                    filter_dict={
                        'language': 'html'
                    }
                )
                logger.info(f"🔍 HTML Code Search (language only): Found {len(html_codes)} HTML files")
            
            # If still no results, try without any filter
            if not html_codes:
                logger.warning(f"⚠️ No HTML files found with language filter, trying without any filter...")
                html_codes = self.embedding_manager.search_similar_code(
                    query="html form input class style",
                    k=100,
                    filter_dict=None
                )
                logger.info(f"🔍 HTML Code Search (no filter): Found {len(html_codes)} HTML files")
        
        if not html_codes:
            logger.warning("⚠️ No HTML code found in codebase - using defaults")
            return self._get_default_html_patterns()
        
        all_html = "\n\n".join([code['content'] for code in html_codes])
        logger.info(f"📝 Combined HTML code size: {len(all_html)} characters")
        logger.info(f"📝 First 500 chars of combined HTML: {all_html[:500]}")
        
        logger.info("🔍 Extracting CSS classes...")
        css_classes = self._extract_common_css_classes(all_html)
        logger.info(f"✅ CSS classes extracted: {len(css_classes)} - {css_classes[:10]}")
        
        return {
            'form_structure': self._extract_form_structure(all_html),
            'input_naming': self._extract_input_naming_pattern(all_html),
            'css_classes': css_classes,
            'button_patterns': self._extract_button_patterns(all_html),
            'table_structure': self._extract_table_structure(all_html),
            # 🆕 12 ESSENTIAL PATTERNS FOR HTML
            'ajax_auto_id': self._extract_ajax_auto_id_generation(all_html),
            'delete_checks': self._extract_delete_dependency_checks(all_html),
            'chart_integration': self._extract_chart_of_accounts_integration(all_html),
            'conditional_logic': self._extract_conditional_code_generation(all_html),
            'dynamic_dropdowns': self._extract_dynamic_dropdown_population(all_html),
            'formvalidation': self._extract_formvalidation_framework(all_html),
            'keyboard_navigation': self._extract_keyboard_navigation(all_html),
            'grid_patterns': self._extract_grid_table_patterns(all_html),
            'disabled_fields': self._extract_disabled_field_handling(all_html),
            'asset_loading': self._extract_complete_asset_loading(all_html),
            'php_includes': self._extract_php_include_files(all_html)
        }
    
    def _extract_form_structure(self, html: str) -> str:
        """Extract common form structure"""
        form_pattern = r'<form[^>]*>.*?</form>'
        forms = re.findall(form_pattern, html, re.DOTALL | re.IGNORECASE)
        
        if forms:
            # Return shortest form (likely the template)
            return min(forms, key=len)[:500]  # Limit length
        
        return '<form method="post" id="form1"></form>'
    
    def _extract_input_naming_pattern(self, html: str) -> Dict:
        """Analyze input field naming conventions"""
        name_pattern = r'name=["\']([^"\']+)["\']'
        names = re.findall(name_pattern, html)
        
        uppercase_count = sum(1 for n in names if n.isupper())
        
        return {
            'uppercase_percent': (uppercase_count / len(names) * 100) if names else 0,
            'uses_uppercase': uppercase_count > len(names) / 2,
            'examples': names[:5]
        }
    
    def _extract_common_css_classes(self, html: str) -> List[str]:
        """Extract CSS classes from HTML code"""
        all_classes = []
        
        # Pattern 1: class="..." attributes
        pattern1 = r'class=["\']([^"\']+)["\']'
        matches = re.findall(pattern1, html, re.IGNORECASE)
        logger.info(f"  Pattern 1 (class=\"...\"): {len(matches)} matches")
        for class_str in matches:
            all_classes.extend(class_str.split())
        
        # Pattern 2: class='...' attributes
        pattern2 = r"class='([^']+)'"
        matches = re.findall(pattern2, html, re.IGNORECASE)
        logger.info(f"  Pattern 2 (class='...'): {len(matches)} matches")
        for class_str in matches:
            all_classes.extend(class_str.split())
        
        # Pattern 3: CSS class definitions in <style> tags
        pattern3 = r'\.([a-zA-Z_][a-zA-Z0-9_-]*)\s*\{'
        matches = re.findall(pattern3, html, re.IGNORECASE)
        logger.info(f"  Pattern 3 (CSS definitions): {len(matches)} matches")
        all_classes.extend(matches)
        
        # Pattern 4: Bootstrap classes (col-*, btn-*, form-*, etc.)
        pattern4 = r'(?:col|btn|form|text|bg|alert|panel|row|container|navbar|modal|card|badge|label|list|table|nav|pagination|progress|spinner|toast|dropdown|popover|tooltip|offcanvas)-[a-zA-Z0-9_-]+'
        matches = re.findall(pattern4, html, re.IGNORECASE)
        logger.info(f"  Pattern 4 (Bootstrap classes): {len(matches)} matches")
        all_classes.extend(matches)
        
        # Pattern 5: Common utility classes
        pattern5 = r'(?:active|disabled|hidden|visible|show|hide|d-none|d-block|d-flex|m-[0-9]|p-[0-9]|mt-[0-9]|mb-[0-9]|ml-[0-9]|mr-[0-9]|pt-[0-9]|pb-[0-9]|pl-[0-9]|pr-[0-9]|w-[0-9]|h-[0-9]|text-center|text-left|text-right|text-justify|float-left|float-right|clearfix|no-wrap|truncate|overflow-hidden|overflow-auto|overflow-scroll)\b'
        matches = re.findall(pattern5, html, re.IGNORECASE)
        logger.info(f"  Pattern 5 (utility classes): {len(matches)} matches")
        all_classes.extend(matches)
        
        # Pattern 6: Custom classes (any word-like class name)
        pattern6 = r'class=["\']([a-zA-Z_][a-zA-Z0-9_-]*)["\']'
        matches = re.findall(pattern6, html, re.IGNORECASE)
        logger.info(f"  Pattern 6 (single classes): {len(matches)} matches")
        all_classes.extend(matches)
        
        # Remove duplicates and empty strings
        all_classes = [c.strip() for c in all_classes if c.strip()]
        unique_classes = list(set(all_classes))
        
        # Count frequency and sort by frequency
        class_counts = Counter(all_classes)
        result = [cls for cls, count in class_counts.most_common(100)]
        
        logger.info(f"🔍 CSS Classes Found (raw): {len(all_classes)} total class references")
        logger.info(f"🔍 CSS Classes Extracted: {len(result)} unique classes")
        if result:
            logger.info(f"   Examples: {result[:15]}")
        
        return result
    
    def _extract_button_patterns(self, html: str) -> List[str]:
        """Extract button patterns"""
        button_pattern = r'<button[^>]*>.*?</button>'
        buttons = re.findall(button_pattern, html, re.DOTALL | re.IGNORECASE)
        
        return buttons[:5]  # Top 5 button examples
    
    def _extract_table_structure(self, html: str) -> str:
        """Extract table structure if exists"""
        table_pattern = r'<table[^>]*>.*?</table>'
        tables = re.findall(table_pattern, html, re.DOTALL | re.IGNORECASE)
        
        if tables:
            return tables[0][:500]  # First table, limited length
        
        return None
    
    async def _analyze_css_patterns(self, codebase_id: str) -> Dict:
        """Extract CSS patterns"""
        logger.info(f"🔍 Starting CSS pattern analysis for codebase: {codebase_id}")
        
        # 🆕 DIRECT ACCESS: Get CSS documents directly from collection
        css_codes = []
        try:
            logger.info(f"🔍 Attempting direct collection access for CSS...")
            collection = self.embedding_manager.vectorstore._collection
            all_docs = collection.get()
            
            if all_docs and all_docs.get('documents'):
                # Filter for CSS documents
                for i, doc in enumerate(all_docs['documents']):
                    metadata = all_docs['metadatas'][i] if all_docs.get('metadatas') else {}
                    
                    # Check if this is a CSS file
                    if metadata.get('language') == 'css':
                        css_codes.append({
                            'content': doc,
                            'metadata': metadata
                        })
                
                logger.info(f"🔍 Direct access found {len(css_codes)} CSS documents")
        except Exception as e:
            logger.warning(f"   Direct collection access failed: {e}")
            css_codes = []
        
        # If direct access didn't work, try search with filters
        if not css_codes:
            logger.info(f"🔍 Falling back to search with codebase_id filter...")
            css_codes = self.embedding_manager.search_similar_code(
                query="css styles",
                k=30,
                filter_dict={
                    'language': 'css',
                    'user_id': str(self.user_id),
                    'codebase_id': str(codebase_id)
                }
            )
            
            logger.info(f"🔍 CSS Code Search (with codebase_id filter): Found {len(css_codes)} CSS files")
            
            if not css_codes:
                logger.warning(f"⚠️ No CSS files found with codebase_id filter, trying without...")
                css_codes = self.embedding_manager.search_similar_code(
                    query="css styles",
                    k=30,
                    filter_dict={
                        'language': 'css',
                        'user_id': str(self.user_id)
                    }
                )
                logger.info(f"🔍 CSS Code Search (without codebase_id): Found {len(css_codes)} CSS files")
        
        if not css_codes:
            logger.warning("⚠️ No CSS code found in codebase - using defaults")
            return self._get_default_css_patterns()
        
        all_css = "\n\n".join([code['content'] for code in css_codes])
        logger.info(f"📝 Combined CSS code size: {len(all_css)} characters")
        
        return {
            'color_scheme': self._extract_color_scheme(all_css),
            'common_classes': self._extract_css_class_definitions(all_css),
            'font_family': self._extract_font_family(all_css),
            'spacing_units': self._extract_spacing_units(all_css)
        }
    
    def _extract_color_scheme(self, css: str) -> List[str]:
        """Extract color palette"""
        color_pattern = r'#[0-9a-fA-F]{3,6}|rgb\([^)]+\)|rgba\([^)]+\)'
        colors = re.findall(color_pattern, css)
        
        # Get unique colors
        unique_colors = list(set(colors))
        
        return unique_colors[:10]
    
    def _extract_css_class_definitions(self, css: str) -> List[str]:
        """Extract CSS class names"""
        class_pattern = r'\.([a-zA-Z_-][a-zA-Z0-9_-]*)\s*\{'
        classes = re.findall(class_pattern, css)
        
        class_counts = Counter(classes)
        
        return [cls for cls, count in class_counts.most_common(20)]
    
    def _extract_font_family(self, css: str) -> str:
        """Extract font family"""
        font_pattern = r'font-family:\s*([^;]+);'
        fonts = re.findall(font_pattern, css, re.IGNORECASE)
        
        if fonts:
            return Counter(fonts).most_common(1)[0][0]
        
        return 'Arial, sans-serif'
    
    def _extract_spacing_units(self, css: str) -> Dict:
        """Analyze spacing units (px, rem, em, %)"""
        px_count = len(re.findall(r'\d+px', css))
        rem_count = len(re.findall(r'\d+rem', css))
        em_count = len(re.findall(r'\d+em', css))
        percent_count = len(re.findall(r'\d+%', css))
        
        total = px_count + rem_count + em_count + percent_count
        
        return {
            'px_percent': (px_count / total * 100) if total > 0 else 0,
            'rem_percent': (rem_count / total * 100) if total > 0 else 0,
            'dominant_unit': 'px' if px_count > rem_count else 'rem'
        }
    
    async def _analyze_js_patterns(self, codebase_id: str) -> Dict:
        """Extract JavaScript patterns"""
        logger.info(f"🔍 Starting JavaScript pattern analysis for codebase: {codebase_id}")
        
        # 🆕 DIRECT ACCESS: Get JS documents directly from collection
        js_codes = []
        try:
            logger.info(f"🔍 Attempting direct collection access for JS...")
            collection = self.embedding_manager.vectorstore._collection
            all_docs = collection.get()
            
            if all_docs and all_docs.get('documents'):
                # Filter for JS documents
                for i, doc in enumerate(all_docs['documents']):
                    metadata = all_docs['metadatas'][i] if all_docs.get('metadatas') else {}
                    
                    # Check if this is a JS file
                    if metadata.get('language') == 'js':
                        js_codes.append({
                            'content': doc,
                            'metadata': metadata
                        })
                
                logger.info(f"🔍 Direct access found {len(js_codes)} JS documents")
        except Exception as e:
            logger.warning(f"   Direct collection access failed: {e}")
            js_codes = []
        
        # If direct access didn't work, try search with filters
        if not js_codes:
            logger.info(f"🔍 Falling back to search with codebase_id filter...")
            js_codes = self.embedding_manager.search_similar_code(
                query="javascript function",
                k=30,
                filter_dict={
                    'language': 'js',
                    'user_id': str(self.user_id),
                    'codebase_id': str(codebase_id)
                }
            )
            
            logger.info(f"🔍 JavaScript Code Search (with codebase_id filter): Found {len(js_codes)} JS files")
            
            if not js_codes:
                logger.warning(f"⚠️ No JS files found with codebase_id filter, trying without...")
                js_codes = self.embedding_manager.search_similar_code(
                    query="javascript function",
                    k=30,
                    filter_dict={
                        'language': 'js',
                        'user_id': str(self.user_id)
                    }
                )
                logger.info(f"🔍 JavaScript Code Search (without codebase_id): Found {len(js_codes)} JS files")
        
        if not js_codes:
            logger.warning("⚠️ No JavaScript code found in codebase - using defaults")
            return self._get_default_js_patterns()
        
        all_js = "\n\n".join([code['content'] for code in js_codes])
        logger.info(f"📝 Combined JavaScript code size: {len(all_js)} characters")
        
        return {
            'functions': self._extract_js_function_names(all_js),
            'ajax_pattern': self._extract_ajax_pattern(all_js),
            'validation_pattern': self._extract_js_validation_pattern(all_js),
            'uses_jquery': '$.ajax' in all_js or '$.post' in all_js or 'jQuery' in all_js,
            'common_variables': self._extract_js_variables(all_js),
            # 🆕 12 ESSENTIAL PATTERNS FOR JAVASCRIPT
            'ajax_auto_id': self._extract_ajax_auto_id_generation(all_js),
            'delete_checks': self._extract_delete_dependency_checks(all_js),
            'chart_integration': self._extract_chart_of_accounts_integration(all_js),
            'conditional_logic': self._extract_conditional_code_generation(all_js),
            'dynamic_dropdowns': self._extract_dynamic_dropdown_population(all_js),
            'formvalidation': self._extract_formvalidation_framework(all_js),
            'keyboard_navigation': self._extract_keyboard_navigation(all_js),
            'grid_patterns': self._extract_grid_table_patterns(all_js),
            'disabled_fields': self._extract_disabled_field_handling(all_js),
            'asset_loading': self._extract_complete_asset_loading(all_js),
            'php_includes': self._extract_php_include_files(all_js)
        }
    
    def _extract_js_function_names(self, code: str) -> List[str]:
        """Extract JavaScript function names"""
        function_pattern = r'function\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\('
        functions = re.findall(function_pattern, code)
        
        return list(set(functions))[:15]
    
    def _extract_ajax_pattern(self, code: str) -> str:
        """Extract AJAX call pattern"""
        patterns = [
            r'\$\.ajax\([^)]+\)',
            r'\$\.post\([^)]+\)',
            r'fetch\([^)]+\)',
            r'XMLHttpRequest'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, code, re.DOTALL)
            if matches:
                return matches[0][:200]  # First match, limited
        
        return '$.post(url, data, callback)'
    
    def _extract_js_validation_pattern(self, code: str) -> List[str]:
        """Extract validation patterns"""
        validation_pattern = r'function\s+(validate[a-zA-Z0-9_]*)\s*\([^)]*\)\s*\{[^}]+\}'
        validations = re.findall(validation_pattern, code, re.DOTALL)
        
        return validations[:3]
    
    def _extract_js_variables(self, code: str) -> List[str]:
        """Extract common variable names"""
        var_pattern = r'\b(var|let|const)\s+([a-zA-Z_][a-zA-Z0-9_]*)'
        variables = re.findall(var_pattern, code)
        
        var_names = [v[1] for v in variables]
        var_counts = Counter(var_names)
        
        return [var for var, count in var_counts.most_common(15)]
    
    async def _analyze_sql_patterns(self, codebase_id: str) -> Dict:
        """Extract SQL patterns"""
        logger.info(f"🔍 Starting SQL pattern analysis for codebase: {codebase_id}")
        
        # 🆕 DIRECT ACCESS: Get SQL documents directly from collection
        sql_codes = []
        try:
            logger.info(f"🔍 Attempting direct collection access for SQL...")
            collection = self.embedding_manager.vectorstore._collection
            all_docs = collection.get()
            
            if all_docs and all_docs.get('documents'):
                # Filter for SQL documents
                for i, doc in enumerate(all_docs['documents']):
                    metadata = all_docs['metadatas'][i] if all_docs.get('metadatas') else {}
                    
                    # Check if this is a SQL file in the requested codebase
                    if (
                        metadata.get('language') == 'sql'
                        and metadata.get('codebase_id') == codebase_id
                    ):
                        sql_codes.append({
                            'content': doc,
                            'metadata': metadata
                        })
                
                logger.info(f"🔍 Direct access found {len(sql_codes)} SQL documents")
        except Exception as e:
            logger.warning(f"   Direct collection access failed: {e}")
            sql_codes = []
        
        # If direct access didn't work, try search with filters
        if not sql_codes:
            logger.info(f"🔍 Falling back to search with codebase_id filter...")
            sql_codes = self.embedding_manager.search_similar_code(
                query="sql create table",
                k=20,
                filter_dict={
                    'language': 'sql',
                    'user_id': str(self.user_id),
                    'codebase_id': str(codebase_id)
                }
            )
            
            logger.info(f"🔍 SQL Code Search (with codebase_id filter): Found {len(sql_codes)} SQL files")
            
            if not sql_codes:
                logger.warning(f"⚠️ No SQL files found with codebase_id filter, trying without...")
                sql_codes = self.embedding_manager.search_similar_code(
                    query="sql create table",
                    k=20,
                    filter_dict={
                        'language': 'sql',
                        'user_id': str(self.user_id)
                    }
                )
                logger.info(f"🔍 SQL Code Search (without codebase_id): Found {len(sql_codes)} SQL files")
        
        if not sql_codes:
            logger.warning("⚠️ No SQL code found in codebase - using defaults")
            return self._get_default_sql_patterns()
        
        all_sql = "\n\n".join([code['content'] for code in sql_codes])
        logger.info(f"📝 Combined SQL code size: {len(all_sql)} characters")
        
        return {
            'engine': self._extract_db_engine(all_sql),
            'charset': self._extract_charset(all_sql),
            'common_datatypes': self._extract_common_datatypes(all_sql),
            'naming_convention': self._extract_sql_naming(all_sql)
        }
    
    def _extract_db_engine(self, sql: str) -> str:
        """Extract database engine"""
        if 'InnoDB' in sql:
            return 'InnoDB'
        elif 'MyISAM' in sql:
            return 'MyISAM'
        return 'InnoDB'
    
    def _extract_charset(self, sql: str) -> str:
        """Extract charset"""
        charset_pattern = r'CHARSET=(\w+)'
        matches = re.findall(charset_pattern, sql, re.IGNORECASE)
        
        if matches:
            return Counter(matches).most_common(1)[0][0]
        
        return 'utf8mb4'
    
    def _extract_common_datatypes(self, sql: str) -> List[str]:
        """Extract commonly used data types"""
        datatype_pattern = r'\b(VARCHAR|INT|TEXT|DATE|DATETIME|DECIMAL|FLOAT|ENUM|TINYINT|BIGINT)\b'
        datatypes = re.findall(datatype_pattern, sql, re.IGNORECASE)
        
        type_counts = Counter([dt.upper() for dt in datatypes])
        
        return [dt for dt, count in type_counts.most_common(10)]
    
    def _extract_sql_naming(self, sql: str) -> str:
        """Analyze SQL naming convention"""
        # Extract table and column names
        table_pattern = r'CREATE TABLE\s+`?([a-zA-Z_][a-zA-Z0-9_]*)`?'
        tables = re.findall(table_pattern, sql, re.IGNORECASE)
        
        if not tables:
            return 'snake_case'
        
        # Check if snake_case or camelCase
        snake_case_count = sum(1 for t in tables if '_' in t)
        
        return 'snake_case' if snake_case_count > len(tables) / 2 else 'camelCase'
    
    # Default patterns (fallback)
    def _get_default_php_patterns(self) -> Dict:
        return {
            'functions': [],
            'table_names': [],
            'field_names': [],
            'ajax_functions': [],
            'db_connection': 'mysqli_connect',
            'session_management': 'session_start()',
            'validation_functions': [],
            'transaction_management': {'start': None, 'end': None},
            'naming_conventions': {'dominant_style': 'camelCase'},
            'common_variables': [],
            'response_patterns': [],
            'include_patterns': []
        }
    
    def _get_default_html_patterns(self) -> Dict:
        return {
            'form_structure': '<form method="post"></form>',
            'input_naming': {'uses_uppercase': False, 'examples': []},
            'css_classes': [],
            'button_patterns': [],
            'table_structure': None
        }
    
    def _get_default_css_patterns(self) -> Dict:
        return {
            'color_scheme': [],
            'common_classes': [],
            'font_family': 'Arial, sans-serif',
            'spacing_units': {'dominant_unit': 'px'}
        }
    
    def _get_default_js_patterns(self) -> Dict:
        return {
            'functions': [],
            'ajax_pattern': '$.post',
            'validation_pattern': [],
            'uses_jquery': True,
            'common_variables': []
        }
    
    def _get_default_sql_patterns(self) -> Dict:
        return {
            'engine': 'InnoDB',
            'charset': 'utf8mb4',
            'common_datatypes': ['VARCHAR', 'INT', 'TEXT', 'DATE'],
            'naming_convention': 'snake_case'
        }
