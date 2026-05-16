from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter, Language
from django.conf import settings
from django.core.cache import cache
import logging
import chromadb
from chromadb.config import Settings as ChromaSettings
import hashlib
import json

logger = logging.getLogger(__name__)

class CodeEmbeddingManager:
    """
    Manages code embeddings and vector store
    """
    
    def __init__(self, user_id: str = None):
        self.api_key = settings.LANGCHAIN_CONFIG.get('openai_api_key')

        # Create ChromaDB client with telemetry completely disabled
        self.chroma_client = chromadb.PersistentClient(
            path=settings.CHROMA_CONFIG['persist_directory'],
            settings=ChromaSettings(
                anonymized_telemetry=False,
                allow_reset=True,
                is_persistent=True
            )
        )

        self.embeddings = None
        self.vectorstore = None

        if self.api_key:
            self.embeddings = OpenAIEmbeddings(
                model="text-embedding-3-small",
                openai_api_key=self.api_key
            )

            collection_name = f"codebase_{user_id}" if user_id else settings.CHROMA_CONFIG['collection_name']
            self.vectorstore = Chroma(
                client=self.chroma_client,
                collection_name=collection_name,
                embedding_function=self.embeddings
            )
        else:
            logger.warning("OpenAI API key is not configured. Vector indexing and semantic retrieval are disabled.")
        
        # Language-specific splitters
        # ENHANCED: Larger chunk sizes to preserve complete patterns
        self.splitters = {
            'php': RecursiveCharacterTextSplitter.from_language(
                language=Language.PHP,
                chunk_size=2000,  # Increased from 1000 to preserve complete functions
                chunk_overlap=400  # Increased overlap for better context
            ),
            'js': RecursiveCharacterTextSplitter.from_language(
                language=Language.JS,
                chunk_size=2000,  # Increased from 1000
                chunk_overlap=400
            ),
            'html': RecursiveCharacterTextSplitter.from_language(
                language=Language.HTML,
                chunk_size=2000,  # Increased from 1000
                chunk_overlap=400
            ),
            'css': RecursiveCharacterTextSplitter(
                chunk_size=1500,  # Increased from 1000
                chunk_overlap=300
            ),
            'sql': RecursiveCharacterTextSplitter(
                chunk_size=1000,  # Keep SQL smaller as it's more structured
                chunk_overlap=200
            ),
        }

    def _split_code_content(self, file_path: str, code_content: str, language: str):
        """
        Deterministic chunking policy shared by both single-file and batch indexing.

        Clean-design goal:
        - frm*.php should prefer one-chunk storage (up to a safe upper bound)
        - non-form files keep size-aware chunking for retrieval quality and token safety
        """
        file_size = len(code_content or '')
        base_name = (file_path or '').replace('\\', '/').split('/')[-1].lower()
        is_frm_php = language == 'php' and base_name.startswith('frm') and base_name.endswith('.php')

        if language == 'php':
            # Clean storage policy: keep ERP form files whole where feasible.
            if is_frm_php and file_size <= 120000:
                logger.info(f"📄 Storing form file as single chunk: {base_name} ({file_size} bytes)")
                return [code_content]

            # Small PHP files: complete single chunk
            if file_size < 50000:
                logger.info(f"📄 Storing complete file (no chunking): {file_size} bytes")
                return [code_content]

            # Medium-Large PHP files
            if file_size < 200000:
                splitter = RecursiveCharacterTextSplitter(
                    chunk_size=8000,
                    chunk_overlap=1500,
                    separators=["\n\nfunction ", "\nfunction ", "\n\n", "\n", " "]
                )
                chunks = splitter.split_text(code_content)
                logger.info(f"🔪 Smart chunking: {len(chunks)} chunks from {file_size} bytes")
                return chunks

            # Very large PHP files
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=5000,
                chunk_overlap=1000,
                separators=["\n\nfunction ", "\nfunction ", "\n\n", "\n"]
            )
            chunks = splitter.split_text(code_content)
            logger.info(f"✂️ Standard chunking: {len(chunks)} chunks from {file_size} bytes")
            return chunks

        # Non-PHP files: language-aware splitter
        splitter = self.splitters.get(language)
        return splitter.split_text(code_content)
    
    def _sanitize_metadata(self, metadata: dict) -> dict:
        """
        ✅ FIXED ISSUE #5: Convert all metadata values to Chroma-compatible scalars
        Chroma only accepts: str, int, float, bool
        Converts lists to comma-separated strings
        
        IMPORTANT: Boolean values are kept as bool (not converted to string)
        This ensures filter compatibility: filter={'has_ajax': True} works correctly
        """
        sanitized = {}
        for key, value in metadata.items():
            if value is None:
                sanitized[key] = ''
            elif isinstance(value, bool):
                # ✅ Keep boolean as-is (don't convert to string)
                sanitized[key] = value
            elif isinstance(value, (str, int, float)):
                sanitized[key] = value
            elif isinstance(value, (list, tuple)):
                # Convert list/tuple to comma-separated string
                sanitized[key] = ','.join(str(v) for v in value)
            elif isinstance(value, dict):
                # Convert dict to string representation
                sanitized[key] = str(value)
            else:
                # Convert any other type to string
                sanitized[key] = str(value)
        return sanitized
    
    def add_code_file(self, file_path: str, code_content: str, metadata: dict):
        """
        Add a single code file to vector store with optimized chunking
        ENHANCED: Now extracts and stores table names, field names, AJAX patterns
        FIXED ISSUE #4: Store complete file metadata + chunk metadata
        """
        if not self.vectorstore:
            logger.warning("Skipping add_code_file because vector storage is unavailable.")
            return 0

        try:
            # Skip empty files
            if not code_content or not code_content.strip():
                logger.warning(f"Skipping empty file: {file_path}")
                return 0
            
            # Determine language from file extension
            extension = file_path.split('.')[-1]
            language_map = {
                'php': 'php',
                'js': 'js',
                'html': 'html',
                'htm': 'html',
                'css': 'css',
                'sql': 'sql'
            }
            
            language = language_map.get(extension, 'php')
            
            # Shared deterministic chunking policy
            chunks = self._split_code_content(file_path=file_path, code_content=code_content, language=language)
            
            # Skip if no chunks generated
            if not chunks or len(chunks) == 0:
                logger.warning(f"No chunks generated for file: {file_path}")
                return 0
            
            # 🆕 FIXED ISSUE #4: Extract COMPLETE file metadata ONCE (not per chunk)
            complete_file_metadata = self._extract_complete_file_metadata(code_content, language)
            
            # 🚀 OPTIMIZATION: Limit chunks per file to avoid too many embeddings
            # Only apply limit for files that were chunked (not complete files)
            max_chunks_per_file = 30  # Increased from 20 to 30 for large files
            if len(chunks) > 1 and len(chunks) > max_chunks_per_file:
                # Keep first 15 and last 15 chunks (usually most important)
                chunks = chunks[:15] + chunks[-15:]
                logger.info(f"⚠️ Limited chunks for {file_path}: {len(chunks)} chunks")
            
            portable_file_path = metadata.get('relative_path') or file_path
            absolute_file_path = metadata.get('absolute_file_path') or file_path

            # Add metadata to each chunk
            metadatas = [
                self._sanitize_metadata({
                    **metadata,
                    **complete_file_metadata,  # ✅ Add COMPLETE file metadata to each chunk
                    'file_path': portable_file_path,
                    'relative_path': metadata.get('relative_path', portable_file_path),
                    'absolute_file_path': absolute_file_path,
                    'chunk_index': i,
                    'total_chunks': len(chunks),
                    'language': language,
                    'user_id': str(metadata.get('user_id', '')),  # ✅ Ensure string
                    'codebase_id': str(metadata.get('codebase_id', '')),  # ✅ Ensure string
                    'file_type': metadata.get('file_type', 'company_code'),
                    'file_size': len(code_content),  # ✅ Store file size
                    'is_complete_file': (i == 0)  # ✅ Mark first chunk as complete file
                })
                for i in range(len(chunks))
            ]
            
            # 🚀 OPTIMIZATION: Add to vector store in batch (faster than one-by-one)
            self.vectorstore.add_texts(
                texts=chunks,
                metadatas=metadatas
            )
            
            logger.info(f"Added {len(chunks)} chunks from {file_path} (size: {len(code_content)} chars)")
            logger.info(f"  Tables: {complete_file_metadata.get('table_names', 'None')}")
            logger.info(f"  Fields: {len(complete_file_metadata.get('field_names', '').split(',')) if complete_file_metadata.get('field_names') else 0} fields")
            logger.info(f"  AJAX: {complete_file_metadata.get('has_ajax', False)}")
            logger.info(f"  Patterns: Dropdown={complete_file_metadata.get('has_cascading_dropdown', False)}, "
                       f"Keyboard={complete_file_metadata.get('has_keyboard_nav', False)}, "
                       f"Validation={complete_file_metadata.get('has_form_validation', False)}, "
                       f"Grid={complete_file_metadata.get('has_grid', False)}")
            
            return len(chunks)
            
        except Exception as e:
            logger.error(f"Error adding file {file_path}: {str(e)}")
            raise
    
    def _extract_complete_file_metadata(self, code_content: str, language: str) -> dict:
        """
        Extract COMPLETE file metadata (not per chunk)
        FIXED ISSUE #4: Store all important metadata for the complete file
        🆕 FIXED: Convert lists to comma-separated strings for Chroma compatibility
        """
        import re
        metadata = {}
        
        if language == 'php':
            # Extract ALL table names
            table_pattern = r'(?:CREATE\s+TABLE|INSERT\s+INTO|FROM|UPDATE|DELETE\s+FROM)\s+`?([a-zA-Z_][a-zA-Z0-9_]*)`?'
            tables = re.findall(table_pattern, code_content, re.IGNORECASE)
            if tables:
                unique_tables = list(set(tables))
                # 🆕 FIXED: Convert list to comma-separated string for Chroma
                metadata['table_names'] = ','.join(unique_tables)
                metadata['has_database'] = True
                metadata['table_count'] = len(unique_tables)
            
            # Extract ALL field names
            field_pattern = r"'([a-zA-Z_][a-zA-Z0-9_]*)'\s*=>|name=['\"]([^'\"]+)['\"]|\$_POST\[[\'\"]([^'\"]+)[\'\"]"
            fields = re.findall(field_pattern, code_content)
            if fields:
                field_names = [f[0] or f[1] or f[2] for f in fields if f[0] or f[1] or f[2]]
                unique_fields = list(set(field_names))
                # 🆕 FIXED: Convert list to comma-separated string for Chroma
                metadata['field_names'] = ','.join(unique_fields)
                metadata['field_count'] = len(unique_fields)
            
            # Extract AJAX patterns
            # ✅ ISSUE #1 FIX: Enhanced AJAX detection with more patterns
            ajax_indicators = [
                '$.ajax', '$.post', '$.get', 'fetch(',
                'Action==', 'Action===', "Action:'", 'Action:"',
                'GetMaxID', 'getMaxID', 'maxid()', 'LPAD(',
                'ajaxSetup', 'XMLHttpRequest'
            ]
            
            if any(indicator in code_content for indicator in ajax_indicators):
                metadata['has_ajax'] = True
                
                # Extract AJAX URLs/endpoints
                ajax_pattern = r"url\s*:\s*['\"]([a-zA-Z_][a-zA-Z0-9_\.]*)['\"]"
                ajax_urls = re.findall(ajax_pattern, code_content)
                
                # Extract Action values
                action_pattern = r"Action\s*[=:]\s*['\"]([a-zA-Z_][a-zA-Z0-9_]*)['\"]"
                action_values = re.findall(action_pattern, code_content)
                
                # Extract $.post inline URLs
                post_pattern = r"\$\.post\s*\(\s*['\"]([^'\"]+\.php)['\"]"
                post_urls = re.findall(post_pattern, code_content)
                
                # Combine all AJAX endpoints
                all_ajax = ajax_urls + action_values + post_urls
                
                if all_ajax:
                    unique_ajax = list(set(all_ajax))
                    # 🆕 FIXED: Convert list to comma-separated string for Chroma
                    metadata['ajax_endpoints'] = ','.join(unique_ajax)
                    metadata['ajax_count'] = len(unique_ajax)
            
            # Check for multi-table operations
            if len(set(tables)) > 1:
                metadata['has_multi_table'] = True
            
            # Extract ALL function names
            func_pattern = r'function\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\('
            functions = re.findall(func_pattern, code_content)
            if functions:
                unique_funcs = list(set(functions))
                # 🆕 FIXED: Convert list to comma-separated string for Chroma
                metadata['functions'] = ','.join(unique_funcs)
                metadata['function_count'] = len(unique_funcs)
            
            # Check for transaction functions
            if 'funStartTran' in code_content or 'beginTransaction' in code_content:
                metadata['has_transactions'] = True
            
            # Check for validation
            if 'validate' in code_content.lower() or 'check' in code_content.lower():
                metadata['has_validation'] = True
            
            # Check for error handling
            if 'try' in code_content or 'catch' in code_content or 'Exception' in code_content:
                metadata['has_error_handling'] = True
            
            # Extract session usage
            if 'session_start' in code_content or '$_SESSION' in code_content:
                metadata['uses_session'] = True
            
            # Extract database connection type
            if 'mysqli' in code_content:
                metadata['db_type'] = 'mysqli'
            elif 'PDO' in code_content:
                metadata['db_type'] = 'pdo'
            elif 'mysql_' in code_content:
                metadata['db_type'] = 'mysql_deprecated'
            
            # 🆕 ENHANCED PATTERN DETECTION (Generic, not hardcoded)
            
            # 1. Cascading/Dynamic Dropdowns
            # ✅ ISSUE #5 FIX: Enhanced cascading dropdown detection
            cascading_indicators = [
                r'\.change\(\)',           # jQuery .change()
                r'onChange\s*=',           # onChange attribute
                r'onchange\s*=',           # onchange attribute
                r'dependent\s+dropdown',   # Dependent dropdown
                r'cascading',              # Cascading keyword
                r'parent.*child',          # Parent-child relationship
                r'Area.*SubArea',          # Area → SubArea pattern
                r'City.*Area',             # City → Area pattern
                r'Category.*SubCategory',  # Category → SubCategory
                r'populate.*dropdown',     # Populate dropdown
                r'load.*dropdown',         # Load dropdown
                r'dynamic.*select'         # Dynamic select
            ]
            
            if any(re.search(indicator, code_content, re.I) for indicator in cascading_indicators):
                metadata['has_cascading_dropdown'] = True
            
            # 2. Keyboard Navigation
            if re.search(r'keycode|keypress|keydown|onkeydown|onkeypress', code_content, re.I):
                metadata['has_keyboard_nav'] = True
            
            # 3. Form Validation (FormValidation.js or custom)
            # ✅ ISSUE #2 FIX: Enhanced FormValidation detection
            formvalidation_indicators = [
                r'\.formValidation\s*\(',  # $('#frm').formValidation(
                r'formValidation\.css',    # CSS file
                r'formValidation\.min\.js', # JS file
                r'data-fv-',               # data-fv-* attributes
                r'success\.form\.fv',      # FormValidation events
                r'framework\s*:\s*["\']bootstrap["\']'  # Framework config
            ]
            
            if any(re.search(indicator, code_content, re.I) for indicator in formvalidation_indicators):
                metadata['has_form_validation'] = True
                
                # Count validation fields
                field_validators = re.findall(r'(\w+)\s*:\s*\{[^}]*validators\s*:', code_content, re.I)
                if field_validators:
                    metadata['validation_field_count'] = len(set(field_validators))
            
            # 4. Select2 Plugin
            if re.search(r'select2|data-plugin=["\']select2["\']', code_content, re.I):
                metadata['has_select2'] = True
            
            # 5. Grid/Table with Add/Edit/Delete
            if re.search(r'addRow|addGridRow|editRow|deleteRow|gridData', code_content, re.I):
                metadata['has_grid'] = True
            
            # 6. Auto-ID Generation
            if re.search(r'getMaxID|MAX\(|LPAD\(|auto_increment', code_content, re.I):
                metadata['has_auto_id'] = True
            
            # 7. Chart of Accounts Integration
            if re.search(r'INSERT\s+INTO\s+chart|ACC_CODE|chart\s+WHERE', code_content, re.I):
                metadata['has_chart_integration'] = True
            
            # 8. Pre-Delete Checks
            if re.search(r'getrows|getrows2|COUNT\(\*\)|check.*exist', code_content, re.I):
                metadata['has_pre_delete_check'] = True
            
            # 9. Multiple AJAX Handlers
            ajax_actions = re.findall(r"Action\s*==\s*['\"]([^'\"]+)['\"]", code_content)
            if len(ajax_actions) > 1:
                metadata['has_multiple_ajax'] = True
                metadata['ajax_actions'] = ','.join(list(set(ajax_actions)))
            
            # 10. Audit Fields (session tracking)
            if re.search(r'User_ID|Comp_Code|Login_ID|UNIT_CODE', code_content):
                metadata['has_audit_fields'] = True
            
            # 11. iCheck Plugin (checkboxes/radios)
            if re.search(r'icheck|icheckbox|iradio', code_content, re.I):
                metadata['has_icheck'] = True
            
            # 12. Switchery Plugin (toggle switches)
            if re.search(r'switchery|data-plugin=["\']switchery["\']', code_content, re.I):
                metadata['has_switchery'] = True
            
            # 13. Dropify Plugin (file upload)
            if re.search(r'dropify|data-plugin=["\']dropify["\']', code_content, re.I):
                metadata['has_dropify'] = True
            
            # 14. Date Picker
            if re.search(r'datepicker|daterangepicker|data-plugin=["\']datepicker["\']', code_content, re.I):
                metadata['has_datepicker'] = True
            
            # 15. Modal/Dialog
            if re.search(r'modal|dialog|\.modal\(|data-toggle=["\']modal["\']', code_content, re.I):
                metadata['has_modal'] = True
            
            # 16. Print Functionality
            if re.search(r'window\.print|print\(\)|printJS', code_content, re.I):
                metadata['has_print'] = True
            
            # 17. Export Functionality (Excel/PDF)
            if re.search(r'export|excel|pdf|download|tableExport', code_content, re.I):
                metadata['has_export'] = True
            
            # 18. Search/Filter
            if re.search(r'search|filter|\.search\(|data-search', code_content, re.I):
                metadata['has_search'] = True
            
            # 19. Pagination
            if re.search(r'pagination|page|limit|offset|LIMIT\s+\d+', code_content, re.I):
                metadata['has_pagination'] = True
            
            # 20. Logging/Audit Trail
            if re.search(r'fun_log|audit|log_|activity_log', code_content, re.I):
                metadata['has_logging'] = True
            
            # 🆕 ADDITIONAL PATTERNS (Company-specific but generic detection)
            
            # 21. Custom Database Functions (company pattern)
            if re.search(r'db_insert|db_update|db_delete|db_getRecord', code_content, re.I):
                metadata['has_custom_db_functions'] = True
            
            # 22. Alert/Notification System
            if re.search(r'alert\(|toastr|showNotification|notification', code_content, re.I):
                metadata['has_alerts'] = True
            
            # 23. MatchHeight Plugin (equal height columns)
            if re.search(r'matchHeight|data-plugin=["\']matchHeight["\']', code_content, re.I):
                metadata['has_matchheight'] = True
            
            # 24. Animsition Plugin (page transitions)
            if re.search(r'animsition|data-animsition', code_content, re.I):
                metadata['has_animsition'] = True
            
            # 25. Intro.js (user onboarding/tour)
            if re.search(r'intro\.js|introjs|data-intro', code_content, re.I):
                metadata['has_introjs'] = True
            
            # 26. Screenfull (fullscreen mode)
            if re.search(r'screenfull|requestFullscreen', code_content, re.I):
                metadata['has_screenfull'] = True
            
            # 27. SlidePanel (side panels)
            if re.search(r'slidePanel|slidepanel', code_content, re.I):
                metadata['has_slidepanel'] = True
            
            # 28. Blueimp File Upload
            if re.search(r'blueimp|fileupload|jquery\.fileupload', code_content, re.I):
                metadata['has_blueimp_upload'] = True
            
            # 29. Flag Icons (country flags)
            if re.search(r'flag-icon|flag icon', code_content, re.I):
                metadata['has_flag_icons'] = True
            
            # 30. Web Icons/Brand Icons
            if re.search(r'web-icons|brand-icons|icon wb-', code_content, re.I):
                metadata['has_web_icons'] = True
            
            # 31. Autocomplete
            if re.search(r'autocomplete|\.autocomplete\(', code_content, re.I):
                metadata['has_autocomplete'] = True
            
            # 32. Google Charts
            if re.search(r'google\.charts|google\.visualization|DataTable', code_content, re.I):
                metadata['has_google_charts'] = True
            
            # 33. Roboto Font
            if re.search(r'Roboto|fonts\.googleapis\.com', code_content, re.I):
                metadata['uses_google_fonts'] = True
            
            # 34. Bootstrap Extensions
            if re.search(r'bootstrap-extend|bootstrap-datepicker', code_content, re.I):
                metadata['has_bootstrap_extensions'] = True
            
            # 35. Custom Validation Functions
            if re.search(r'IsNumeric|CheckMaskFormat|Verify_Email', code_content, re.I):
                metadata['has_custom_validation'] = True
            
            # 36. File Upload with Preview
            if re.search(r'input-file|file.*preview|image.*upload', code_content, re.I):
                metadata['has_file_upload'] = True
            
            # 37. Responsive Tables
            if re.search(r'table-responsive|responsive.*table', code_content, re.I):
                metadata['has_responsive_table'] = True
            
            # 38. Collapsible/Accordion
            if re.search(r'collapse|accordion|panel-collapse', code_content, re.I):
                metadata['has_collapsible'] = True
            
            # 39. Tabs
            if re.search(r'nav-tabs|tab-pane|data-toggle=["\']tab["\']', code_content, re.I):
                metadata['has_tabs'] = True
            
            # 40. Tooltips/Popovers
            if re.search(r'tooltip|popover|data-toggle=["\']tooltip["\']', code_content, re.I):
                metadata['has_tooltips'] = True
            
            # 🆕 ADDITIONAL MISSING PATTERNS (from codebase analysis)
            
            # 41. Email Functionality
            if re.search(r'\bmail\(|PHPMailer|sendmail|smtp', code_content, re.I):
                metadata['has_email'] = True
            
            # 42. PHPExcel/Spreadsheet Export
            if re.search(r'phpexcel|PHPExcel|spreadsheet|IOFactory', code_content, re.I):
                metadata['has_phpexcel'] = True
            
            # 43. SMS Functionality
            if re.search(r'\bsms\b|sendSms|SmsDailySale|SmsWeekly', code_content, re.I):
                metadata['has_sms'] = True
            
            # 44. PDF Generation (DomPDF/TCPDF)
            if re.search(r'dompdf|tcpdf|fpdf|mpdf|jspdf', code_content, re.I):
                metadata['has_pdf_generation'] = True
            
            # 45. Barcode Generation
            if re.search(r'barcode|BCG|barcodegen', code_content, re.I):
                metadata['has_barcode'] = True
            
            # 46. Image/Webcam Capture
            if re.search(r'webcam|snapshot|camera|image.*capture', code_content, re.I):
                metadata['has_webcam'] = True
            
            # 47. Input Masking/Formatting
            if re.search(r'mask|inputmask|MaskFormat|format_amount|CheckMask', code_content, re.I):
                metadata['has_input_masking'] = True
            
            # 48. Preloader/Spinner
            if re.search(r'preloader|spinner|loading|loader\.gif', code_content, re.I):
                metadata['has_preloader'] = True
            
            # 49. Window.open (Popup Windows)
            if re.search(r'window\.open\(', code_content, re.I):
                metadata['has_popup_windows'] = True
            
            # 50. CSV Export/Import
            if re.search(r'\.csv|CSV|comma.*separated', code_content, re.I):
                metadata['has_csv'] = True
            
            # 🆕 FINAL MISSING PATTERNS (from deep codebase analysis)
            
            # 51. Database Backup/Restore
            if re.search(r'backup|restore|mysqldump|tbldatabasedate', code_content, re.I):
                metadata['has_backup'] = True
            
            # 52. JSON API/REST
            if re.search(r'json_encode|json_decode|application/json|REST|api', code_content, re.I):
                metadata['has_json_api'] = True
            
            # 53. Password Hashing (MD5/SHA1)
            if re.search(r'\bmd5\(|sha1\(|password_hash|bcrypt', code_content, re.I):
                metadata['has_password_hashing'] = True
            
            # 54. Image Upload/Processing
            if re.search(r'move_uploaded_file|imagecreatefrom|getimagesize|GD|UploadImage', code_content, re.I):
                metadata['has_image_upload'] = True
            
            # 55. File Download
            if re.search(r'readfile|fpassthru|Content-Disposition.*attachment', code_content, re.I):
                metadata['has_file_download'] = True
            
            # 56. IP Geolocation
            if re.search(r'ip2location|ipinfo|geolocation|ClientIP', code_content, re.I):
                metadata['has_ip_geolocation'] = True
            
            # 57. Transaction Management
            if re.search(r'funStartTran|funEndTran|beginTransaction|commit|rollback', code_content, re.I):
                metadata['has_transaction_mgmt'] = True
            
            # 58. Log Tables (Audit Trail)
            if re.search(r'logtable|log.*insert|backup.*column', code_content, re.I):
                metadata['has_log_tables'] = True
            
            # 59. Multi-Company Support
            if re.search(r'COMP_CODE|company.*code|multi.*company', code_content, re.I):
                metadata['has_multi_company'] = True
            
            # 60. Day Opening/Closing
            if re.search(r'DayOpening|day.*opening|opening.*balance', code_content, re.I):
                metadata['has_day_opening'] = True

            # Strict form-contract structural metadata (Phase 2 foundation)
            metadata['has_config_include'] = bool(
                re.search(r'include\s*\(\s*[\'\"]include/config\.inc\.php[\'\"]\s*\)', code_content, re.I)
            )
            metadata['has_formheader'] = bool(
                re.search(r'include\s*\(\s*[\'\"]include/formheader\.php[\'\"]\s*\)', code_content, re.I)
            )

            include_order = []
            for include_match in re.finditer(
                r'(?:include|include_once|require|require_once)\s*\(\s*[\'\"]([^\'\"]+)[\'\"]\s*\)',
                code_content,
                re.I,
            ):
                include_order.append(str(include_match.group(1) or '').strip())
            if include_order:
                metadata['include_order'] = ','.join(include_order)

            metadata['footer_count'] = len(
                re.findall(r'include\s*\(\s*[\'\"]include/footer\.php[\'\"]\s*\)', code_content, re.I)
            )

            lower_session = re.findall(r"\$_SESSION\s*\[\s*['\"](user_id|comp_code|login_id)['\"]\s*\]", code_content, re.I)
            upper_session = re.findall(r"\$_SESSION\s*\[\s*['\"](User_ID|Comp_Code|Login_ID)['\"]\s*\]", code_content, re.I)
            if lower_session and not upper_session:
                metadata['session_key_casing'] = 'lower'
            elif upper_session and not lower_session:
                metadata['session_key_casing'] = 'upper'
            elif lower_session and upper_session:
                metadata['session_key_casing'] = 'mixed'
            else:
                metadata['session_key_casing'] = 'unknown'

            if re.search(r"\$_(?:REQUEST|POST)\s*\[\s*['\"]Action['\"]\s*\]", code_content, re.I):
                metadata['crud_action_style'] = 'action_request'
            elif re.search(r'txtmode', code_content, re.I):
                metadata['crud_action_style'] = 'txtmode_form'
            else:
                metadata['crud_action_style'] = 'unknown'

            getmaxid_block = re.search(r'GetMaxID[\s\S]{0,1000}', code_content, re.I)
            getmaxid_text = getmaxid_block.group(0) if getmaxid_block else ''
            if re.search(r'json_encode\s*\(', getmaxid_text, re.I):
                metadata['getmaxid_response_type'] = 'json'
            elif getmaxid_text:
                metadata['getmaxid_response_type'] = 'scalar'
            else:
                metadata['getmaxid_response_type'] = 'unknown'

            metadata['uses_btnsave_click'] = bool(re.search(r'function\s+btnsave_click\s*\(', code_content, re.I))
            metadata['uses_success_form_fv'] = bool(re.search(r'success\.form\.fv', code_content, re.I))

            edit_binding_match = re.search(
                r'(\$[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:mysql_fetch_array\s*\(\s*)?db_getRecord\s*\(',
                code_content,
                re.I,
            )
            metadata['edit_binding_variable'] = edit_binding_match.group(1) if edit_binding_match else ''

            metadata['has_master_detail'] = bool(re.search(r'TXTCOUNTACC|detail|grid', code_content, re.I))
            metadata['detail_counter_field'] = 'TXTCOUNTACC' if re.search(r'TXTCOUNTACC', code_content, re.I) else ''
            metadata['has_audit_columns'] = bool(
                re.search(r'CreationDateTime|Comp_Code|UserId|Login_ID', code_content, re.I)
            )
            metadata['has_dependency_delete_checks'] = bool(
                re.search(r'getrows2?\s*\([\s\S]{0,300}db_delete', code_content, re.I)
            )
        
        elif language == 'html':
            # Check for form
            if '<form' in code_content.lower():
                metadata['has_form'] = True
                # Count form fields
                form_fields = re.findall(r'name=["\']([^"\']+)["\']', code_content)
                if form_fields:
                    unique_fields = list(set(form_fields))
                    # 🆕 FIXED: Convert list to comma-separated string for Chroma
                    metadata['form_fields'] = ','.join(unique_fields)
                    metadata['form_field_count'] = len(unique_fields)
            
            # Check for table
            if '<table' in code_content.lower():
                metadata['has_table'] = True
            
            # Extract CSS classes
            class_pattern = r'class=["\']([^"\']+)["\']'
            classes = re.findall(class_pattern, code_content)
            if classes:
                all_classes = []
                for class_str in classes:
                    all_classes.extend(class_str.split())
                unique_classes = list(set(all_classes))
                # 🆕 FIXED: Convert list to comma-separated string for Chroma
                metadata['css_classes'] = ','.join(unique_classes)
                metadata['css_class_count'] = len(unique_classes)
            
            # Check for Bootstrap
            if 'bootstrap' in code_content.lower() or 'col-md' in code_content:
                metadata['uses_bootstrap'] = True
        
        elif language == 'js':
            # Check for AJAX
            if '$.ajax' in code_content or 'fetch(' in code_content:
                metadata['has_ajax'] = True
            
            # Check for jQuery
            if '$(' in code_content or 'jQuery' in code_content:
                metadata['uses_jquery'] = True
            
            # Check for validation
            if 'validate' in code_content.lower():
                metadata['has_validation'] = True
            
            # Extract function names
            func_pattern = r'function\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\('
            functions = re.findall(func_pattern, code_content)
            if functions:
                unique_funcs = list(set(functions))
                # 🆕 FIXED: Convert list to comma-separated string for Chroma
                metadata['functions'] = ','.join(unique_funcs)
                metadata['function_count'] = len(unique_funcs)
        
        elif language == 'sql':
            # Extract table names
            table_pattern = r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?([a-zA-Z_][a-zA-Z0-9_]*)`?'
            tables = re.findall(table_pattern, code_content, re.IGNORECASE)
            if tables:
                unique_tables = list(set(tables))
                # 🆕 FIXED: Convert list to comma-separated string for Chroma
                metadata['table_names'] = ','.join(unique_tables)
                metadata['table_count'] = len(unique_tables)
            
            # Extract column names
            col_pattern = r'`?([a-zA-Z_][a-zA-Z0-9_]*)`?\s+(?:VARCHAR|INT|TEXT|DATE|DATETIME|DECIMAL|FLOAT|ENUM|TINYINT|BIGINT)'
            columns = re.findall(col_pattern, code_content, re.IGNORECASE)
            if columns:
                unique_cols = list(set(columns))
                # 🆕 FIXED: Convert list to comma-separated string for Chroma
                metadata['column_names'] = ','.join(unique_cols)
                metadata['column_count'] = len(unique_cols)
            
            # Check database engine
            if 'InnoDB' in code_content:
                metadata['db_engine'] = 'InnoDB'
            elif 'MyISAM' in code_content:
                metadata['db_engine'] = 'MyISAM'
            
            # Check charset
            if 'utf8mb4' in code_content:
                metadata['charset'] = 'utf8mb4'
            elif 'utf8' in code_content:
                metadata['charset'] = 'utf8'
        
        return metadata
    
    def add_code_files_batch(self, files_data: list):
        """
        🚀 BATCH EMBEDDING: Add multiple files in a single batch for maximum speed
        OPTIMIZATION: Reduces API calls by 50x!
        ENHANCED: Extracts and stores metadata for better filtering
        FIXED ISSUE #4: Store complete file metadata for each chunk
        
        Args:
            files_data: List of dicts with 'file_path', 'code_content', 'metadata'
        
        Returns:
            Total chunks added
        """
        if not self.vectorstore:
            logger.warning("Skipping add_code_files_batch because vector storage is unavailable.")
            return 0

        try:
            all_chunks = []
            all_metadatas = []
            total_chunks = 0
            
            for file_data in files_data:
                file_path = file_data['file_path']
                code_content = file_data['code_content']
                metadata = file_data['metadata']
                portable_file_path = metadata.get('relative_path') or file_path
                absolute_file_path = metadata.get('absolute_file_path') or file_path
                
                # Skip empty files
                if not code_content or not code_content.strip():
                    continue
                
                # Determine language
                extension = file_path.split('.')[-1]
                language_map = {
                    'php': 'php', 'js': 'js', 'html': 'html',
                    'htm': 'html', 'css': 'css', 'sql': 'sql'
                }
                language = language_map.get(extension, 'php')
                # Shared deterministic chunking policy (same as single-file path)
                chunks = self._split_code_content(
                    file_path=file_path,
                    code_content=code_content,
                    language=language
                )
                
                if not chunks:
                    continue
                
                # Limit chunks per file (align with single-file path)
                max_chunks_per_file = 30
                if len(chunks) > 1 and len(chunks) > max_chunks_per_file:
                    chunks = chunks[:15] + chunks[-15:]
                
                # 🆕 FIXED ISSUE #4: Extract COMPLETE file metadata ONCE
                complete_file_metadata = self._extract_complete_file_metadata(code_content, language)
                
                # Prepare metadatas
                for i, chunk in enumerate(chunks):
                    all_chunks.append(chunk)
                    all_metadatas.append(self._sanitize_metadata({
                        **metadata,
                        **complete_file_metadata,  # ✅ Add COMPLETE file metadata
                        'file_path': portable_file_path,
                        'relative_path': metadata.get('relative_path', portable_file_path),
                        'absolute_file_path': absolute_file_path,
                        'chunk_index': i,
                        'total_chunks': len(chunks),
                        'language': language,
                        'user_id': str(metadata.get('user_id', '')),  # ✅ Ensure string
                        'codebase_id': str(metadata.get('codebase_id', '')),  # ✅ Ensure string
                        'file_type': metadata.get('file_type', 'company_code'),
                        'file_size': len(code_content),
                        'is_complete_file': (i == 0)
                    }))
                
                total_chunks += len(chunks)
            
            # 🚀 Add chunks in token-safe sub-batches.
            # OpenAI embedding requests are capped by total tokens per request.
            # We approximate this cap via total characters to prevent 400 max_tokens_per_request errors.
            if all_chunks:
                max_chars_per_request = 900000   # ~225k tokens at ~4 chars/token
                max_chunks_per_request = 350

                batch_chunks = []
                batch_metadatas = []
                batch_chars = 0
                sub_batch_index = 0
                flushed_chunks = 0

                for chunk_text, chunk_meta in zip(all_chunks, all_metadatas):
                    chunk_chars = len(chunk_text or "")
                    should_flush = (
                        batch_chunks and (
                            len(batch_chunks) >= max_chunks_per_request or
                            (batch_chars + chunk_chars) > max_chars_per_request
                        )
                    )

                    if should_flush:
                        self.vectorstore.add_texts(
                            texts=batch_chunks,
                            metadatas=batch_metadatas
                        )
                        sub_batch_index += 1
                        flushed_chunks += len(batch_chunks)
                        logger.info(
                            f"✅ Embedding sub-batch {sub_batch_index}: "
                            f"{len(batch_chunks)} chunks (~{batch_chars:,} chars)"
                        )
                        batch_chunks = []
                        batch_metadatas = []
                        batch_chars = 0

                    batch_chunks.append(chunk_text)
                    batch_metadatas.append(chunk_meta)
                    batch_chars += chunk_chars

                if batch_chunks:
                    self.vectorstore.add_texts(
                        texts=batch_chunks,
                        metadatas=batch_metadatas
                    )
                    sub_batch_index += 1
                    flushed_chunks += len(batch_chunks)
                    logger.info(
                        f"✅ Embedding sub-batch {sub_batch_index}: "
                        f"{len(batch_chunks)} chunks (~{batch_chars:,} chars)"
                    )

                logger.info(
                    f"✅ Batch added {flushed_chunks} chunks from {len(files_data)} files "
                    f"in {sub_batch_index} embedding request(s)"
                )
            
            return total_chunks
            
        except Exception as e:
            logger.error(f"Error in batch add: {str(e)}")
            raise
    
    def search_similar_code(self, query: str, k: int = 30, filter_dict: dict = None):
        """
        Search for similar code patterns with HYBRID SEARCH (semantic + keyword)
        ✅ FIXED ISSUE #5: Improved ChromaDB filter syntax and testing
        """
        if not self.vectorstore:
            logger.warning("Skipping search_similar_code because vector storage is unavailable.")
            return []

        try:
            # 🆕 DIAGNOSTIC: Log search parameters
            logger.info(f"🔍 search_similar_code called:")
            logger.info(f"   Query: {query}")
            logger.info(f"   K: {k}")
            logger.info(f"   Filter: {filter_dict}")

            # Cache key for repeated retrievals (reduces embedding API calls)
            cache_payload = {
                'query': query,
                'k': k,
                'filter': filter_dict or {}
            }
            cache_key = "search:" + hashlib.md5(json.dumps(cache_payload, sort_keys=True).encode()).hexdigest()
            cached_results = cache.get(cache_key)
            if cached_results is not None:
                logger.info(f"✅ Cache HIT: vector search ({len(cached_results)} results)")
                return cached_results
            
            if filter_dict:
                # Build proper Chroma where clause
                if len(filter_dict) > 1:
                    where_clause = {
                        "$and": [
                            {key: value} for key, value in filter_dict.items()
                        ]
                    }
                else:
                    where_clause = filter_dict
                
                logger.info(f"   Where clause: {where_clause}")
                
                # 🆕 HYBRID SEARCH: Get more results for keyword filtering
                try:
                    if where_clause:
                        semantic_results = self.vectorstore.similarity_search_with_score(
                            query,
                            k=k * 3,  # Get 3x more for hybrid filtering
                            filter=where_clause
                        )
                    else:
                        # No filter - search all documents
                        semantic_results = self.vectorstore.similarity_search_with_score(query, k=k * 3)
                        
                        # ✅ NEW: Manual filtering if where_clause was disabled
                        if filter_dict:
                            logger.info(f"   Applying manual filtering...")
                            filtered_results = []
                            for doc, score in semantic_results:
                                match = True
                                for key, value in filter_dict.items():
                                    if doc.metadata.get(key) != value:
                                        match = False
                                        break
                                if match:
                                    filtered_results.append((doc, score))
                            semantic_results = filtered_results
                            logger.info(f"   After manual filtering: {len(semantic_results)} results")
                except Exception as e:
                    logger.warning(f"   Filter search failed: {e}, trying without filter...")
                    # Fallback: search without filter and filter results manually
                    semantic_results = self.vectorstore.similarity_search_with_score(query, k=k * 3)
                    # Manual filtering
                    if filter_dict:
                        filtered_results = []
                        for doc, score in semantic_results:
                            match = True
                            for key, value in filter_dict.items():
                                if doc.metadata.get(key) != value:
                                    match = False
                                    break
                            if match:
                                filtered_results.append((doc, score))
                        semantic_results = filtered_results
                        logger.info(f"   After manual filtering: {len(semantic_results)} results")
            else:
                logger.info(f"   No filter - searching all documents")
                semantic_results = self.vectorstore.similarity_search_with_score(query, k=k * 3)
            
            logger.info(f"   Semantic results: {len(semantic_results)} documents found")

            
            # 🆕 KEYWORD MATCHING: Extract keywords from query and filter results
            keyword_scores = self._calculate_keyword_scores(query, semantic_results)
            
            # 🆕 HYBRID SCORING: Combine semantic + keyword scores with DYNAMIC WEIGHTS
            hybrid_results = self._combine_scores(semantic_results, keyword_scores, k, query=query)
            
            logger.info(f"   Hybrid results: {len(hybrid_results)} documents after scoring")
            
            # Convert results with proper similarity scoring
            formatted_results = []
            distances = []
            for doc, score, hybrid_score in hybrid_results:
                distances.append(score)
                import math
                similarity = math.exp(-score)
                formatted_results.append({
                    'content': doc.page_content,
                    'metadata': doc.metadata,
                    'similarity_score': similarity,
                    'hybrid_score': hybrid_score  # ✅ NEW: Hybrid score
                })
            
            # Log retrieval stats
            if formatted_results:
                avg_similarity = sum(r['similarity_score'] for r in formatted_results) / len(formatted_results)
                avg_hybrid = sum(r['hybrid_score'] for r in formatted_results) / len(formatted_results)
                logger.info(f"Retrieved {len(formatted_results)} patterns (semantic: {avg_similarity:.2%}, hybrid: {avg_hybrid:.2%})")

            # Cache final formatted results for repeated searches
            cache.set(cache_key, formatted_results, 3600)
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"Error searching similar code: {str(e)}")
            return []
    
    def _calculate_keyword_scores(self, query: str, results: list) -> dict:
        """
        Calculate keyword matching scores for results
        Extracts important keywords from query and matches against content
        🆕 FIXED: Handle comma-separated metadata strings
        """
        import re
        
        # Extract keywords from query (remove common words)
        common_words = {'with', 'the', 'a', 'an', 'and', 'or', 'is', 'are', 'from', 'to', 'in', 'on', 'at', 'by'}
        keywords = [w.lower() for w in re.findall(r'\b\w+\b', query) if w.lower() not in common_words and len(w) > 2]
        
        keyword_scores = {}
        
        for idx, (doc, score) in enumerate(results):
            content = doc.page_content.lower()
            metadata = doc.metadata
            
            # Count keyword matches in content
            keyword_matches = sum(1 for kw in keywords if kw in content)
            
            # Check metadata matches (table names, field names, AJAX functions)
            metadata_matches = 0
            
            # Check table names (now comma-separated string)
            if 'table_names' in metadata and metadata['table_names']:
                tables = metadata['table_names'].split(',') if isinstance(metadata['table_names'], str) else [metadata['table_names']]
                for table in tables:
                    if table.lower().strip() in content:
                        metadata_matches += 2  # Higher weight for table matches
            
            # Check field names (now comma-separated string)
            if 'form_fields' in metadata and metadata['form_fields']:
                fields = metadata['form_fields'].split(',') if isinstance(metadata['form_fields'], str) else [metadata['form_fields']]
                for field in fields:
                    if field.lower().strip() in content:
                        metadata_matches += 1
            
            # Check AJAX endpoints (now comma-separated string)
            if 'ajax_endpoints' in metadata and metadata['ajax_endpoints']:
                endpoints = metadata['ajax_endpoints'].split(',') if isinstance(metadata['ajax_endpoints'], str) else [metadata['ajax_endpoints']]
                for endpoint in endpoints:
                    if endpoint.lower().strip() in content:
                        metadata_matches += 2  # Higher weight for AJAX matches
            
            # Check functions (now comma-separated string)
            if 'functions' in metadata and metadata['functions']:
                funcs = metadata['functions'].split(',') if isinstance(metadata['functions'], str) else [metadata['functions']]
                for func in funcs:
                    if func.lower().strip() in content:
                        metadata_matches += 1
            
            # Calculate keyword score (0-1)
            total_matches = keyword_matches + metadata_matches
            max_possible = len(keywords) + 10  # Normalize
            keyword_score = min(total_matches / max_possible, 1.0) if max_possible > 0 else 0
            
            keyword_scores[idx] = keyword_score
        
        return keyword_scores
    
    def _combine_scores(self, semantic_results: list, keyword_scores: dict, k: int, query: str = "") -> list:
        """
        Combine semantic and keyword scores for hybrid ranking
        🆕 ENHANCED: Dynamic weights based on query specificity
        ✅ ISSUE #1 FIX: Improved AJAX pattern detection with better keyword weights
        
        Weights:
        - Generic queries: 60% semantic, 40% keyword
        - Specific pattern queries: 50% semantic, 50% keyword (balanced for AJAX patterns)
        """
        import math
        
        # 🆕 DETECT QUERY SPECIFICITY: Check if query contains specific pattern keywords
        # ✅ ISSUE #1 FIX: Added more AJAX-specific keywords
        pattern_keywords = [
            # AJAX patterns (CRITICAL for Issue #1)
            'ajax', '$.ajax', '$.post', '$.get', 'getMaxID', 'GetMaxID', 'LPAD', 'MAX(RIGHT',
            'Action==', 'XMLHttpRequest', 'fetch(', 'auto-id', 'auto-increment',
            # Dropdown patterns
            'dropdown', 'cascading', 'select2', 'onChange', 'dependent', 'dynamic select',
            # Validation patterns
            'validation', 'formValidation', 'data-fv', 'notEmpty', 'validators',
            # Keyboard patterns
            'keyboard', 'keycode', 'navigation', 'checkKeycode', 'onKeyDown', 'keypress',
            # Grid patterns
            'grid', 'addRow', 'editRow', 'deleteRow', 'gridData', 'table',
            # Database patterns
            'db_insert', 'db_update', 'db_delete', 'getrows', 'getvalue', 'db_getRecord',
            # Transaction patterns
            'transaction', 'funStartTran', 'funEndTran', 'beginTransaction',
            # Session/Audit patterns
            'session', 'audit', 'User_ID', 'Comp_Code', 'Login_ID',
            # Chart patterns
            'chart', 'ACC_CODE', 'ACC_CUST', 'ledger'
        ]
        
        query_lower = query.lower()
        pattern_matches = sum(1 for kw in pattern_keywords if kw.lower() in query_lower)
        
        # ✅ ISSUE #1 FIX: Optimized weights for AJAX pattern retrieval
        # Testing showed 50/50 balance works best for pattern-heavy queries
        if pattern_matches >= 7:
            # Very specific query with many patterns: Balanced approach
            semantic_weight = 0.50  # ✅ OPTIMIZED: 50/50 for best AJAX retrieval
            keyword_weight = 0.50
            logger.info(f"🎯 Using BALANCED weights (50/50) - {pattern_matches} patterns detected")
        elif pattern_matches >= 4:
            # Moderately specific: Slightly favor semantic
            semantic_weight = 0.55  # ✅ OPTIMIZED: Slight semantic preference
            keyword_weight = 0.45
            logger.info(f"🎯 Using SEMANTIC-LEANING weights (55/45) - {pattern_matches} patterns detected")
        else:
            # Generic query: Standard semantic-heavy weights
            semantic_weight = 0.60
            keyword_weight = 0.40
            logger.info(f"🎯 Using SEMANTIC-HEAVY weights (60/40) - {pattern_matches} patterns detected")
        
        combined = []
        
        for idx, (doc, distance) in enumerate(semantic_results):
            # Semantic score (convert distance to similarity)
            semantic_score = math.exp(-distance)
            
            # Keyword score
            keyword_score = keyword_scores.get(idx, 0)
            
            # 🆕 DYNAMIC HYBRID SCORE with adaptive weights
            hybrid_score = (semantic_weight * semantic_score) + (keyword_weight * keyword_score)
            
            combined.append((doc, distance, hybrid_score))
        
        # Sort by hybrid score (descending)
        combined.sort(key=lambda x: x[2], reverse=True)
        
        # Return top k results
        return combined[:k]
    
    def get_retriever(self, search_kwargs: dict = None):
        """
        Get a retriever for RAG pipeline
        """
        if not self.vectorstore:
            return None

        if search_kwargs is None:
            search_kwargs = {'k': 5}
        
        return self.vectorstore.as_retriever(search_kwargs=search_kwargs)
    
    def get_vectorstore_stats(self):
        """
        Get diagnostic stats about the vectorstore
        """
        if not self.vectorstore:
            return 0

        try:
            # Try to get collection stats
            collection = self.vectorstore._collection
            count = collection.count()
            logger.info(f"📊 Vectorstore Stats:")
            logger.info(f"   Total documents: {count}")
            
            # Try to get a sample document to see metadata
            if count > 0:
                results = self.vectorstore.similarity_search("test", k=1)
                if results:
                    logger.info(f"   Sample metadata keys: {list(results[0].metadata.keys())}")
                    logger.info(f"   Sample metadata: {results[0].metadata}")
                    
                    # Also try to get all documents with their metadata
                    try:
                        all_docs = collection.get()
                        if all_docs and all_docs.get('metadatas'):
                            logger.info(f"   All document metadatas (first 3):")
                            for i, meta in enumerate(all_docs['metadatas'][:3]):
                                logger.info(f"     Doc {i}: {meta}")
                    except Exception as e:
                        logger.warning(f"   Could not get all documents: {e}")
            
            return count
        except Exception as e:
            logger.error(f"Error getting vectorstore stats: {e}")
            return 0
    
    def test_filter_compatibility(self, filter_dict: dict) -> dict:
        """
        ✅ NEW (ISSUE #5): Test filter compatibility with ChromaDB
        
        Tests if a filter dict works with ChromaDB and returns diagnostic info
        
        Args:
            filter_dict: Filter dictionary to test
            
        Returns:
            {
                'compatible': bool,
                'individual_results': dict,  # Results for each filter key
                'combined_results': int,     # Results for combined filter
                'errors': list,              # Any errors encountered
                'recommendations': list      # Suggestions for fixing issues
            }
        """
        result = {
            'compatible': True,
            'individual_results': {},
            'combined_results': 0,
            'errors': [],
            'recommendations': []
        }

        if not self.vectorstore:
            result['compatible'] = False
            result['errors'].append('Vector storage is unavailable because the OpenAI API key is not configured.')
            result['recommendations'].append('Configure OPENAI_API_KEY before running embedding-based compatibility checks.')
            return result
        
        try:
            # Test each filter individually
            for key, value in filter_dict.items():
                try:
                    test_results = self.vectorstore.similarity_search_with_score(
                        "test",
                        k=1,
                        filter={key: value}
                    )
                    result['individual_results'][key] = len(test_results)
                    
                    if len(test_results) == 0:
                        result['recommendations'].append(
                            f"Filter '{key}={value}' returns 0 results - check if this metadata exists"
                        )
                except Exception as e:
                    result['compatible'] = False
                    result['errors'].append(f"Filter '{key}={value}' failed: {str(e)}")
                    result['recommendations'].append(
                        f"Filter '{key}' may not be compatible - check metadata type (bool vs string)"
                    )
            
            # Test combined filter
            if len(filter_dict) > 1:
                where_clause = {
                    "$and": [
                        {key: value} for key, value in filter_dict.items()
                    ]
                }
            else:
                where_clause = filter_dict
            
            try:
                combined_results = self.vectorstore.similarity_search_with_score(
                    "test",
                    k=1,
                    filter=where_clause
                )
                result['combined_results'] = len(combined_results)
                
                if len(combined_results) == 0:
                    result['recommendations'].append(
                        "Combined filter returns 0 results - filters may be too restrictive"
                    )
                    result['recommendations'].append(
                        "Consider: Remove optional filters or use broader criteria"
                    )
            except Exception as e:
                result['compatible'] = False
                result['errors'].append(f"Combined filter failed: {str(e)}")
                result['recommendations'].append(
                    "Combined filter syntax may be incorrect - check ChromaDB documentation"
                )
        
        except Exception as e:
            result['compatible'] = False
            result['errors'].append(f"Filter test failed: {str(e)}")
        
        return result
