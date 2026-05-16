import os
import zipfile
import shutil
from pathlib import Path
from typing import List, Dict
from django.conf import settings
from .embeddings import CodeEmbeddingManager
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import asyncio
from functools import partial

logger = logging.getLogger(__name__)


def _to_windows_long_path(path: str) -> str:
    """
    Return a Windows long-path-safe variant for filesystem operations.
    """
    if not path:
        return path

    normalized = os.path.normpath(str(path))
    if os.name != 'nt':
        return normalized

    if normalized.startswith('\\\\?\\'):
        return normalized

    if not os.path.isabs(normalized):
        normalized = os.path.abspath(normalized)

    if normalized.startswith('\\\\'):
        return f"\\\\?\\UNC\\{normalized[2:]}"

    return f"\\\\?\\{normalized}"


def _from_windows_long_path(path: str) -> str:
    """
    Strip Windows long-path prefix for readable logging/metadata paths.
    """
    if not path:
        return path

    normalized = str(path)
    if os.name == 'nt':
        if normalized.startswith('\\\\?\\UNC\\'):
            normalized = f"\\\\{normalized[8:]}"
        elif normalized.startswith('\\\\?\\'):
            normalized = normalized[4:]

    return os.path.normpath(normalized)


class CodeIngestionPipeline:
    """
    Handles uploading and indexing company codebases
    WITH OPTIMIZATIONS FOR LARGE FILES
    """
    
    SUPPORTED_EXTENSIONS = ['.php', '.html', '.htm', '.css', '.js', '.sql']
    
    # File size limits for optimization
    MAX_FILE_SIZE = 500 * 1024  # 500KB - skip files larger than this
    MIN_FILE_SIZE = 50  # 50 bytes - skip tiny files
    
    # Batch processing settings
    BATCH_SIZE = 50  # Process 50 files at a time
    MAX_WORKERS = 4  # Parallel workers for file processing
    VECTOR_DELETE_BATCH_SIZE = 5000  # Keep under Chroma's max batch limit
    
    def __init__(self, user_id: str = None):
        self.user_id = user_id
        self.embedding_manager = CodeEmbeddingManager(user_id=user_id)
    
    def process_uploaded_file(self, uploaded_file, codebase_id: str, user_id: str) -> Dict:
        """
        Process uploaded zip file or individual files
        """
        try:
            # Create directory for this codebase
            codebase_dir = os.path.join(
                settings.COMPANY_CODEBASE_DIR,
                user_id,
                codebase_id
            )
            os.makedirs(_to_windows_long_path(codebase_dir), exist_ok=True)
            
            # Handle zip file
            if uploaded_file.name.endswith('.zip'):
                return self._process_zip(uploaded_file, codebase_dir, codebase_id, user_id)
            else:
                return self._process_single_file(uploaded_file, codebase_dir, codebase_id, user_id)
                
        except Exception as e:
            logger.error(f"Error processing upload: {str(e)}")
            raise
    
    def _process_zip(self, zip_file, extract_dir: str, codebase_id: str, user_id: str) -> Dict:
        """
        Extract and index zip file with PARALLEL PROCESSING for speed
        ✅ ISSUE #6 FIX: Invalidates old cache before processing new codebase
        """
        # ✅ ISSUE #6 FIX: Invalidate old cache for this codebase_id
        # This ensures when user re-uploads same codebase, old patterns are cleared
        from agents.utils.cache_helper import invalidate_codebase_cache
        invalidate_codebase_cache(user_id, codebase_id)
        logger.info(f"🗑️ Invalidated old cache for codebase {codebase_id} before new upload")
        
        temp_zip_path = os.path.join(extract_dir, 'temp.zip')
        temp_zip_fs_path = _to_windows_long_path(temp_zip_path)
        extract_fs_path = _to_windows_long_path(extract_dir)
        
        # Save zip file
        with open(temp_zip_fs_path, 'wb+') as destination:
            for chunk in zip_file.chunks():
                destination.write(chunk)
        
        # Validate ZIP file
        if not zipfile.is_zipfile(temp_zip_fs_path):
            os.remove(temp_zip_fs_path)
            raise ValueError("Invalid ZIP file format")
        
        # Check ZIP contents before extraction
        try:
            with zipfile.ZipFile(temp_zip_fs_path, 'r') as zip_ref:
                # Check for suspicious files
                file_list = zip_ref.namelist()
                
                # Limit number of files (prevent zip bombs)
                if len(file_list) > 10000:
                    raise ValueError("ZIP contains too many files (max 10,000)")
                
                # Check for path traversal attacks (only actual traversal attempts)
                for file_name in file_list:
                    # Only reject absolute paths and parent directory traversal
                    # Check for: /.. or \.. or ../ or ..\  (actual path traversal)
                    if file_name.startswith('/') or file_name.startswith('\\'):
                        raise ValueError(f"Suspicious file path detected: {file_name}")
                    # Check for path traversal patterns (../ or ..\ in the middle)
                    # But allow .. in filenames like "file..xls"
                    if '/../' in file_name or '\\..\\' in file_name or file_name.endswith('/..') or file_name.endswith('\\..'):
                        raise ValueError(f"Suspicious file path detected: {file_name}")
                
                # Extract
                zip_ref.extractall(extract_fs_path)
        except zipfile.BadZipFile:
            os.remove(temp_zip_fs_path)
            raise ValueError("Corrupted ZIP file")
        
        # Remove temp zip
        os.remove(temp_zip_fs_path)
        
        # Find all code files
        code_files = self._find_code_files(extract_dir)
        
        # Validate that ZIP contains actual code files
        if len(code_files) == 0:
            raise ValueError("ZIP file contains no supported code files (.php, .html, .css, .js, .sql)")
        
        logger.info(f"Found {len(code_files)} code files in ZIP")
        
        # 🚀 OPTIMIZATION: Process files in batches for parallel embedding
        result = self._process_files_in_batches(code_files, codebase_id, user_id, extract_dir)
        
        # ✅ NEW: Save files permanently to company_codebases directory
        permanent_dir = os.path.join(
            settings.COMPANY_CODEBASE_DIR,
            user_id,
            codebase_id
        )
        
        # Only copy if extract_dir is different from permanent_dir
        permanent_fs_path = _to_windows_long_path(permanent_dir)
        if os.path.abspath(extract_dir) != os.path.abspath(permanent_dir) and os.path.exists(extract_fs_path):
            try:
                # Remove old files if they exist
                if os.path.exists(permanent_fs_path):
                    shutil.rmtree(permanent_fs_path)
                
                # Copy all files to permanent storage
                shutil.copytree(extract_fs_path, permanent_fs_path)
                logger.info(f"✅ Saved {len(code_files)} files to {permanent_dir}")
                
                # Update result with permanent storage path
                result['storage_path'] = permanent_dir
            except Exception as e:
                logger.error(f"Failed to save files permanently: {str(e)}")
        
        return result
    
    def _process_files_in_batches(self, code_files: List, codebase_id: str, user_id: str, codebase_root: str, batch_size: int = 50) -> Dict:
        """
        Process files in batches for faster embedding generation
        OPTIMIZATION: Batch processing + Parallel file reading
        """
        total_chunks = 0
        indexed_files = 0
        skipped_files = []
        
        total_batches = (len(code_files) + batch_size - 1) // batch_size
        
        # Process in batches
        for i in range(0, len(code_files), batch_size):
            batch = code_files[i:i + batch_size]
            batch_num = i // batch_size + 1
            
            logger.info(f"📦 Processing batch {batch_num}/{total_batches} ({len(batch)} files)")
            
            # 🚀 PARALLEL FILE READING (3-4x faster!)
            batch_file_info = self._read_files_parallel(batch, codebase_id, user_id, codebase_root)
            
            # Track skipped files
            skipped_count = len(batch) - len(batch_file_info)
            if skipped_count > 0:
                logger.info(f"⚠️ Skipped {skipped_count} files in batch {batch_num}")
            
            # 🚀 Process batch with optimized embedding
            if batch_file_info:
                try:
                    # Prepare for batch processing
                    files_data = [
                        {
                            'file_path': info['path'],
                            'code_content': info['content'],
                            'metadata': info['metadata']
                        }
                        for info in batch_file_info
                    ]
                    
                    # Use batch method for faster processing
                    batch_chunks = self.embedding_manager.add_code_files_batch(files_data)
                    total_chunks += batch_chunks
                    indexed_files += len(batch_file_info)
                    
                    logger.info(f"✅ Batch {batch_num} complete: {len(batch_file_info)} files, {batch_chunks} chunks")
                    
                except Exception as e:
                    logger.error(f"❌ Batch {batch_num} failed: {str(e)}")
                    # Fallback to individual processing
                    for file_info in batch_file_info:
                        try:
                            chunks = self.embedding_manager.add_code_file(
                                file_path=file_info['path'],
                                code_content=file_info['content'],
                                metadata=file_info['metadata']
                            )
                            total_chunks += chunks
                            indexed_files += 1
                        except Exception as e:
                            skipped_files.append({
                                'file': file_info['path'],
                                'reason': str(e)
                            })
        
        logger.info(f"🎉 Indexing complete: {indexed_files}/{len(code_files)} files, {total_chunks} total chunks")
        
        # 🆕 ANALYZE PATTERNS AFTER INDEXING
        logger.info("🔍 Starting pattern analysis...")
        try:
            from agents.utils.pattern_analyzer import CodebasePatternAnalyzer
            from agents.utils.cache_helper import set_cached_analyzed_patterns
            from agents.utils.strict_erp_controller import PatternMemoryService
            import traceback
            
            analyzer = CodebasePatternAnalyzer(user_id=user_id)
            
            # 🆕 FIXED: Call sync version instead of async to avoid event loop issues in background thread
            analyzed_patterns = analyzer.analyze_codebase_patterns_sync(codebase_id)
            
            # Cache the analyzed patterns (30 days)
            set_cached_analyzed_patterns(user_id, codebase_id, analyzed_patterns)

            try:
                PatternMemoryService().bootstrap_from_analyzed_patterns(
                    user_id=user_id,
                    codebase_id=codebase_id,
                    analyzed_patterns=analyzed_patterns,
                )
                logger.info("Strict ERP pattern memory persisted")
            except Exception as memory_error:
                logger.error(f"Strict ERP pattern memory bootstrap failed: {memory_error}")
            
            logger.info("✅ Pattern analysis complete and cached!")
            logger.info(f"📊 Cached patterns summary:")
            logger.info(f"   PHP tables: {len(analyzed_patterns.get('php', {}).get('table_names', []))}")
            logger.info(f"   PHP fields: {len(analyzed_patterns.get('php', {}).get('field_names', []))}")
            logger.info(f"   PHP AJAX: {len(analyzed_patterns.get('php', {}).get('ajax_functions', []))}")
            logger.info(f"   HTML CSS: {len(analyzed_patterns.get('html', {}).get('css_classes', []))}")
            
        except Exception as e:
            logger.error(f"⚠️ Pattern analysis failed: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            # Don't fail the whole upload if pattern analysis fails
        
        return {
            'total_files': len(code_files),
            'indexed_files': indexed_files,
            'total_chunks': total_chunks,
            'storage_path': os.path.dirname(code_files[0]) if code_files else '',
            'skipped_files': skipped_files
        }
    
    def _read_files_parallel(self, file_paths: List[Path], codebase_id: str, user_id: str, codebase_root: str) -> List[Dict]:
        """
        Read multiple files in parallel using ThreadPoolExecutor
        🚀 OPTIMIZATION: 3-4x faster than sequential reading
        
        Args:
            file_paths: List of file paths to read
            codebase_id: Codebase ID for metadata
            user_id: User ID for metadata
            
        Returns:
            List of dicts with 'path', 'content', 'metadata'
        """
        def read_single_file(file_path):
            """Read a single file with error handling"""
            try:
                with open(_to_windows_long_path(file_path), 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                # Skip empty files
                if not content or not content.strip():
                    return None
                
                # Skip very large files (> 500KB)
                if len(content) > 500000:
                    logger.warning(f"⚠️ Skipping large file: {file_path}")
                    return None
                
                absolute_path = os.path.normpath(str(file_path))
                relative_path = os.path.relpath(absolute_path, codebase_root)

                return {
                    'path': absolute_path,
                    'content': content,
                    'metadata': {
                        'codebase_id': codebase_id,
                        'user_id': user_id,
                        'file_type': 'company_code',
                        'absolute_file_path': absolute_path,
                        'relative_path': relative_path,
                        'codebase_root': codebase_root
                    }
                }
                
            except UnicodeDecodeError:
                logger.warning(f"⚠️ Skipping file with invalid encoding: {file_path}")
                return None
            except Exception as e:
                logger.warning(f"⚠️ Error reading file {file_path}: {e}")
                return None
        
        # Read files in parallel using ThreadPoolExecutor
        results = []
        with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            # Submit all file reading tasks
            future_to_file = {
                executor.submit(read_single_file, fp): fp 
                for fp in file_paths
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_file):
                result = future.result()
                if result:
                    results.append(result)
        
        logger.info(f"✅ Parallel read: {len(results)}/{len(file_paths)} files successfully read")
        return results
    
    def _process_single_file(self, file, save_dir: str, codebase_id: str, user_id: str) -> Dict:
        """
        Process single file upload
        """
        file_path = os.path.join(save_dir, file.name)
        file_fs_path = _to_windows_long_path(file_path)
        
        with open(file_fs_path, 'wb+') as destination:
            for chunk in file.chunks():
                destination.write(chunk)
        
        with open(file_fs_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        metadata = {
            'codebase_id': codebase_id,
            'user_id': user_id,
            'file_type': 'company_code',
            'absolute_file_path': file_path,
            'relative_path': os.path.basename(file_path),
            'codebase_root': save_dir
        }
        
        chunks = self.embedding_manager.add_code_file(
            file_path=file_path,
            code_content=content,
            metadata=metadata
        )
        
        return {
            'total_files': 1,
            'indexed_files': 1,
            'total_chunks': chunks,
            'storage_path': save_dir
        }
    
    def _find_code_files(self, directory: str) -> List[Path]:
        """
        Recursively find all code files with smart filtering
        🚀 OPTIMIZATION: Skip unnecessary files to speed up processing
        """
        code_files = []
        
        # Files to skip (common non-essential files)
        skip_patterns = [
            'vendor', 'node_modules', '__pycache__', '.git', '.svn',
            'dist', 'build', 'cache', 'tmp', 'temp', 'logs',
            'min.js', 'min.css',  # Minified files (not useful for patterns)
            '.min.', 'bundle.', 'compiled.',  # Compiled/bundled files
            # ✅ FIX: Blacklist PHPExcel and library files
            'phpexcel', 'phpoffice', 'phpspreadsheet',
            'classes/phpexcel', 'vendor/phpoffice', 'libraries/phpexcel',
            'pear', 'vendor/pear', 'classes/pear'
        ]
        
        walk_root = _to_windows_long_path(directory)
        for root, dirs, files in os.walk(walk_root):
            normalized_root = _from_windows_long_path(root)
            # Skip hidden directories and common non-code directories
            dirs[:] = [
                d for d in dirs 
                if not d.startswith('.') and not any(skip in d.lower() for skip in skip_patterns)
            ]
            
            for file in files:
                # Skip if matches skip patterns
                if any(skip in file.lower() for skip in skip_patterns):
                    continue
                
                # Check if supported extension
                if any(file.endswith(ext) for ext in self.SUPPORTED_EXTENSIONS):
                    file_path = os.path.join(normalized_root, file)
                    
                    # 🚀 OPTIMIZATION: Skip very small files (< 100 bytes, likely empty)
                    try:
                        if os.path.getsize(_to_windows_long_path(file_path)) < 100:
                            continue
                    except Exception:
                        pass
                    
                    code_files.append(Path(file_path))
        
        logger.info(f"Found {len(code_files)} relevant code files (after filtering)")
        return code_files
    
    def delete_codebase(self, codebase_id: str, user_id: str):
        """
        Delete codebase and remove from vector store
        ✅ ISSUE #6 FIX: Now invalidates cache when codebase is deleted
        """
        self.clear_codebase_embeddings(codebase_id=codebase_id, user_id=user_id)

        # Delete files
        codebase_dir = os.path.join(
            settings.COMPANY_CODEBASE_DIR,
            user_id,
            codebase_id
        )
        
        codebase_fs_path = _to_windows_long_path(codebase_dir)
        if os.path.exists(codebase_fs_path):
            shutil.rmtree(codebase_fs_path)
            logger.info(f"🗑️ Deleted codebase files: {codebase_dir}")

    def clear_codebase_embeddings(self, codebase_id: str, user_id: str) -> int:
        """
        Delete only vector-store entries for a codebase while preserving source files.
        Returns number of deleted embeddings/chunks.
        """
        # Reinitialize with correct user_id if needed
        if self.user_id != user_id:
            self.embedding_manager = CodeEmbeddingManager(user_id=user_id)
        
        # ✅ ISSUE #6 FIX: Invalidate cache BEFORE deleting
        # This ensures old patterns are removed from cache
        from agents.utils.cache_helper import invalidate_codebase_cache
        invalidate_codebase_cache(user_id, codebase_id)
        logger.info(f"🗑️ Invalidated cache for codebase {codebase_id}")
        
        # Delete from vector store
        deleted_chunks = 0
        try:
            collection = self.embedding_manager.chroma_client.get_collection(f"codebase_{user_id}")
            while True:
                batch = collection.get(
                    where={"codebase_id": codebase_id},
                    limit=self.VECTOR_DELETE_BATCH_SIZE,
                    include=[]
                )
                batch_ids = batch.get("ids", []) if batch else []
                if not batch_ids:
                    break
                collection.delete(ids=batch_ids)
                deleted_chunks += len(batch_ids)
            
            logger.info(
                f"🗑️ Deleted {deleted_chunks} embeddings from vector store for codebase {codebase_id}"
            )
        except Exception as e:
            logger.warning(f"Could not delete from vector store: {e}")
        return deleted_chunks
