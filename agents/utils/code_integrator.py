"""
🆕 SIMPLIFIED: Code integrator for Complete PHP-only generation
Handles single inline PHP file with embedded HTML, CSS, JS
"""

import os
import logging
from typing import Dict, Any
from django.conf import settings

logger = logging.getLogger(__name__)


class CodeIntegrator:
    """
    🆕 SIMPLIFIED: Integrates complete PHP file only (company style)
    """
    
    async def integrate_code(self, generated_code: Dict[str, str], intent: Dict[str, Any], project_id: str) -> Dict[str, Any]:
        """
        🆕 SIMPLIFIED: Integrate complete PHP file only
        
        Args:
            generated_code: Dict with 'complete_php' key
            intent: Parsed user intent
            project_id: Project ID
            
        Returns:
            Dict with integrated code and file structure
        """
        try:
            # Get complete PHP code
            complete_php = generated_code.get('complete_php', '')
            
            if not complete_php:
                logger.error("No complete PHP code provided")
                raise ValueError("No complete PHP code to integrate")
            
            # Get feature name from intent
            feature_name = intent.get('database', {}).get('table_name', 'unknown')
            
            # Create simple file structure
            file_structure = {
                'root': f"{feature_name}_module",
                'files': {
                    'complete_php': {
                        'name': f"frm{feature_name.title()}.php",
                        'path': f"frm{feature_name.title()}.php",
                        'description': 'Complete PHP file with inline HTML, CSS, JS (company style)'
                    }
                }
            }
            
            # Generate deployment guide
            deployment_guide = self._generate_deployment_guide(feature_name)
            
            logger.info(f"Code integration completed for project {project_id}")
            logger.info(f"   📄 File: frm{feature_name.title()}.php ({len(complete_php)} chars)")
            
            return {
                'code': {'complete_php': complete_php},
                'file_structure': file_structure,
                'deployment_guide': deployment_guide
            }
            
        except Exception as e:
            logger.error(f"Error integrating code: {str(e)}")
            raise
    
    def _generate_deployment_guide(self, feature_name: str) -> str:
        """
        🆕 SIMPLIFIED: Generate deployment guide for complete PHP file
        """
        guide = f"""# Deployment Guide - {feature_name.title()} Form

## File Generated
- `frm{feature_name.title()}.php` - Complete PHP file with embedded HTML, CSS, and JavaScript

## Company Standard Structure
This file follows your company's inline PHP+HTML structure:
- PHP logic at the top (session, includes, database operations)
- HTML form below with embedded PHP tags
- JavaScript inline in `<script>` tags
- CSS via `<link>` tags or inline `<style>` tags
- Everything in ONE file (company standard)

## Deployment Steps

### 1. Upload File
```bash
# Upload to your web server
scp frm{feature_name.title()}.php user@server:/path/to/webroot/
```

### 2. Set Permissions
```bash
chmod 644 frm{feature_name.title()}.php
```

### 3. Database Setup
- Ensure database tables already exist (company standard)
- Tables should follow naming convention: `tbl{feature_name.lower()}`
- Required fields: Code, Comp_Code, Created_By, Created_Date

### 4. Configuration
- Verify `include/config.inc.php` exists with database connection
- Ensure session is configured properly
- Check company functions are available (db_insert, db_update, db_delete, etc.)

### 5. Access Form
```
http://yourserver/frm{feature_name.title()}.php
```

## Requirements
- PHP 7.0+
- MySQL database with existing tables
- Web server (Apache/Nginx)
- Company's standard includes:
  - `include/config.inc.php` (database connection)
  - Company functions (db_insert, db_update, db_delete, getvalue, getrows)
  - Session management

## Features Included
- ✅ CRUD operations (Create, Read, Update, Delete)
- ✅ AJAX auto-ID generation
- ✅ Multi-company support (Comp_Code filtering)
- ✅ Session-based audit trails
- ✅ Form validation
- ✅ Bootstrap responsive design
- ✅ Company standard patterns

## Troubleshooting
- Check PHP error logs: `/var/log/php/error.log`
- Verify database connection in config.inc.php
- Ensure all company includes are present
- Check file permissions (should be 644)

## Security Notes
- File uses company's standard security patterns
- Session validation included
- SQL injection protection via company functions
- Multi-company data isolation (Comp_Code)
"""
        
        return guide
