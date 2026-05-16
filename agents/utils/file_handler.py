import os
import re
from typing import Dict, Optional
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class StandardsFileHandler:
    """
    Handles MD standards file parsing and loading
    """
    
    def save_standards_file(self, uploaded_file, standards_id: str, user_id: str) -> Dict:
        """
        Save uploaded MD file
        """
        try:
            standards_dir = os.path.join(
                settings.STANDARDS_DIR,
                user_id
            )
            os.makedirs(standards_dir, exist_ok=True)
            
            file_path = os.path.join(standards_dir, f"{standards_id}.md")
            
            with open(file_path, 'wb+') as destination:
                for chunk in uploaded_file.chunks():
                    destination.write(chunk)
            
            # Parse content
            content = self.load_standards_file(file_path)
            metadata = self.parse_standards_metadata(content)
            
            return {
                'file_path': file_path,
                'content': content,
                'metadata': metadata
            }
            
        except Exception as e:
            logger.error(f"Error saving standards file: {str(e)}")
            raise
    
    def load_standards_file(self, file_path: str) -> str:
        """
        Load MD file content
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error loading standards file: {str(e)}")
            return ""
    
    def parse_standards_metadata(self, content: str) -> Dict:
        """
        Extract metadata from MD file
        """
        metadata = {
            'php_version': '',
            'framework': '',
            'css_framework': '',
            'db_engine': 'InnoDB',
            'charset': 'utf8mb4',
            'js_libraries': []
        }
        
        # Extract PHP version
        php_match = re.search(r'PHP\s+Version[:\s]+(\d+\.\d+)', content, re.IGNORECASE)
        if php_match:
            metadata['php_version'] = php_match.group(1)
        
        # Extract framework
        framework_match = re.search(r'Framework[:\s]+(\w+)', content, re.IGNORECASE)
        if framework_match:
            metadata['framework'] = framework_match.group(1)
        
        # Extract CSS framework
        css_match = re.search(r'CSS Framework[:\s]+(\w+)', content, re.IGNORECASE)
        if css_match:
            metadata['css_framework'] = css_match.group(1)
        
        # Extract DB engine
        db_match = re.search(r'Database Engine[:\s]+(\w+)', content, re.IGNORECASE)
        if db_match:
            metadata['db_engine'] = db_match.group(1)
        
        return metadata
    
    def get_standards_for_user(self, user_id: str, standards_id: Optional[str] = None) -> Dict:
        """
        Get standards file for a user
        """
        standards_dir = os.path.join(settings.STANDARDS_DIR, user_id)
        
        if not os.path.exists(standards_dir):
            return {'content': '', 'metadata': {}}
        
        if standards_id:
            file_path = os.path.join(standards_dir, f"{standards_id}.md")
        else:
            # Get the most recent standards file
            files = [f for f in os.listdir(standards_dir) if f.endswith('.md')]
            if not files:
                return {'content': '', 'metadata': {}}
            
            latest_file = max(files, key=lambda f: os.path.getctime(os.path.join(standards_dir, f)))
            file_path = os.path.join(standards_dir, latest_file)
        
        if not os.path.exists(file_path):
            return {'content': '', 'metadata': {}}
        
        content = self.load_standards_file(file_path)
        metadata = self.parse_standards_metadata(content)
        
        return {
            'content': content,
            'metadata': metadata,
            'file_path': file_path
        }
