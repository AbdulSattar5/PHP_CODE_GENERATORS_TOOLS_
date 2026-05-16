"""
Code pattern retriever for GenCode AI
Retrieves relevant code patterns from vector database
"""

import logging
from typing import List, Dict, Any, Optional
from langchain_openai import OpenAIEmbeddings
import chromadb
from chromadb.config import Settings
from django.conf import settings

logger = logging.getLogger(__name__)


class CodePatternRetriever:
    """
    Retrieves relevant code patterns from indexed company codebase
    """
    
    def __init__(self):
        self.api_key = settings.LANGCHAIN_CONFIG.get('openai_api_key')
        self.embedding_model = None
        if self.api_key:
            self.embedding_model = OpenAIEmbeddings(
                model="text-embedding-3-small",
                openai_api_key=self.api_key
            )

        self.chroma_client = chromadb.PersistentClient(
            path=settings.CHROMA_CONFIG['persist_directory'],
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True,
                is_persistent=True
            )
        )
    
    async def retrieve_patterns(self, query: str, user_id: str, top_k: int = 10, language: Optional[str] = None, codebase_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Retrieve relevant code patterns based on query
        ✅ ISSUE #7 FIX: Added 100% DYNAMIC filename matching bonus
        
        Args:
            query: Search query
            user_id: User ID to filter patterns
            top_k: Number of patterns to retrieve
            language: Optional language filter
            codebase_id: Optional codebase ID filter (if user has multiple codebases)
            
        Returns:
            List of relevant code patterns (sorted by filename match → similarity)
        """
        try:
            if not self.embedding_model:
                logger.warning("Skipping semantic pattern retrieval because the OpenAI API key is not configured.")
                return []

            collection_name = f"codebase_{user_id}"
            
            # Check if collection exists
            try:
                collection = self.chroma_client.get_collection(collection_name)
            except:
                logger.info(f"No codebase collection found for user {user_id}")
                return []
            
            # Create query embedding using OpenAI embeddings
            query_embedding = self.embedding_model.embed_query(query)
            
            # Build where clause for ChromaDB
            # ChromaDB requires $and operator for multiple conditions
            where_conditions = [{"user_id": user_id}]
            
            if language:
                where_conditions.append({"language": language})
            
            if codebase_id:
                where_conditions.append({"codebase_id": str(codebase_id)})
            
            where_clause = {"$and": where_conditions} if len(where_conditions) > 1 else where_conditions[0]
            
            # Query the collection (get more results for re-ranking)
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k * 2,  # ✅ Get 2x results for re-ranking
                where=where_clause if where_clause else None,
                include=['documents', 'metadatas', 'distances']
            )
            
            # Format results with filename bonus
            patterns = []
            query_lower = query.lower()
            
            if results['ids'] and results['ids'][0]:
                for i in range(len(results['ids'][0])):
                    similarity = 1 - results['distances'][0][i]
                    file_path = results['metadatas'][0][i].get('file_path', '')
                    
                    # ✅ ISSUE #7 FIX: Calculate 100% DYNAMIC filename matching bonus
                    filename_bonus = self._calculate_filename_bonus(file_path, query_lower)
                    
                    pattern = {
                        'id': results['ids'][0][i],
                        'code': results['documents'][0][i],
                        'metadata': results['metadatas'][0][i],
                        'similarity': similarity,
                        'filename_bonus': filename_bonus,  # ✅ NEW
                        'language': results['metadatas'][0][i].get('language', 'unknown'),
                        'file_path': file_path,
                        'purpose': results['metadatas'][0][i].get('purpose', ''),
                        'category': results['metadatas'][0][i].get('category', 'General'),
                        'description': self._generate_pattern_description(results['metadatas'][0][i])
                    }
                    patterns.append(pattern)
            
            # ✅ ISSUE #7 FIX: Sort by filename bonus FIRST, then similarity
            patterns.sort(
                key=lambda x: (x['filename_bonus'], x['similarity']),
                reverse=True
            )
            
            # Return top k after re-ranking
            patterns = patterns[:top_k]
            
            logger.info(f"✅ Retrieved {len(patterns)} patterns for query: {query[:50]}... (codebase_id: {codebase_id})")
            if patterns and patterns[0]['filename_bonus'] > 0:
                logger.info(f"   🎯 Top result: {patterns[0]['file_path']} (bonus: {patterns[0]['filename_bonus']}, similarity: {patterns[0]['similarity']:.2f})")
            
            return patterns
            
        except Exception as e:
            logger.error(f"Error retrieving patterns: {str(e)}")
            return []
    
    async def retrieve_patterns_by_category(self, category: str, user_id: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieve patterns by category
        """
        try:
            collection_name = f"codebase_{user_id}"
            
            try:
                collection = self.chroma_client.get_collection(collection_name)
            except:
                return []
            
            # Query by category with proper where clause
            results = collection.get(
                where={
                    "$and": [
                        {"user_id": user_id},
                        {"category": category}
                    ]
                },
                limit=top_k,
                include=['documents', 'metadatas']
            )
            
            patterns = []
            if results['ids']:
                for i in range(len(results['ids'])):
                    pattern = {
                        'id': results['ids'][i],
                        'code': results['documents'][i],
                        'metadata': results['metadatas'][i],
                        'language': results['metadatas'][i].get('language', 'unknown'),
                        'file_path': results['metadatas'][i].get('file_path', ''),
                        'purpose': results['metadatas'][i].get('purpose', ''),
                        'category': results['metadatas'][i].get('category', 'General'),
                        'description': self._generate_pattern_description(results['metadatas'][i])
                    }
                    patterns.append(pattern)
            
            return patterns
            
        except Exception as e:
            logger.error(f"Error retrieving patterns by category: {str(e)}")
            return []
    
    async def retrieve_patterns_by_language(self, language: str, user_id: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieve patterns by programming language
        """
        try:
            collection_name = f"codebase_{user_id}"
            
            try:
                collection = self.chroma_client.get_collection(collection_name)
            except:
                return []
            
            # Query by language with proper where clause
            results = collection.get(
                where={
                    "$and": [
                        {"user_id": user_id},
                        {"language": language}
                    ]
                },
                limit=top_k,
                include=['documents', 'metadatas']
            )
            
            patterns = []
            if results['ids']:
                for i in range(len(results['ids'])):
                    pattern = {
                        'id': results['ids'][i],
                        'code': results['documents'][i],
                        'metadata': results['metadatas'][i],
                        'language': results['metadatas'][i].get('language', 'unknown'),
                        'file_path': results['metadatas'][i].get('file_path', ''),
                        'purpose': results['metadatas'][i].get('purpose', ''),
                        'category': results['metadatas'][i].get('category', 'General'),
                        'description': self._generate_pattern_description(results['metadatas'][i])
                    }
                    patterns.append(pattern)
            
            return patterns
            
        except Exception as e:
            logger.error(f"Error retrieving patterns by language: {str(e)}")
            return []
    
    def _calculate_filename_bonus(self, file_path: str, query_lower: str) -> int:
        """
        ✅ ISSUE #9 FIX: Enhanced filename matching with PascalCase support
        
        This is 100% DYNAMIC - works for ANY entity (Customer, Product, Invoice, SubArea, etc.)
        NO HARDCODED entity lists!
        
        Handles PascalCase: frmSubArea.php matches "SubArea", "sub area", "subarea"
        
        Args:
            file_path: Full file path (e.g., "company_codebases/1/.../frmSubArea.php")
            query_lower: Lowercase search query
            
        Returns:
            Bonus score (0-3):
            - 0: No match
            - 1: Standard naming convention (frm*.php)
            - 2: Exact entity match in filename
            - 3: Exact entity match + standard naming
        """
        if not file_path:
            return 0
        
        # ✅ CRITICAL FIX: Handle both Windows (\) and Unix (/) path separators
        import os
        filename = os.path.basename(file_path)  # Preserve case
        filename_lower = filename.lower()
        bonus = 0
        
        # Bonus 1: Standard naming convention (frm*.php, tbl*.php, rpt*.php)
        if filename_lower.startswith(('frm', 'tbl', 'rpt')) and filename_lower.endswith('.php'):
            bonus += 1
            
            # Bonus 2: DYNAMIC entity matching from query with PascalCase support
            # Extract entity name from filename (e.g., frmSubArea.php → SubArea)
            prefix_len = 3  # Length of 'frm', 'tbl', 'rpt'
            entity_in_filename = filename[prefix_len:-4]  # Remove prefix and '.php' suffix (preserve case)
            entity_in_filename_lower = entity_in_filename.lower()
            
            # ✅ ISSUE #9 FIX: Check multiple variations for better matching
            if entity_in_filename and len(entity_in_filename) > 2:  # At least 3 chars
                
                # Check 1: Exact match (case-insensitive)
                if entity_in_filename_lower in query_lower:
                    bonus += 2
                    logger.info(f"   🎯 EXACT match: {filename} entity '{entity_in_filename}' found in query")
                
                # Check 2: PascalCase match (SubArea matches "sub area" or "subarea")
                # Convert PascalCase to space-separated (SubArea → sub area)
                else:
                    import re
                    entity_spaced = re.sub(r'([A-Z])', r' \1', entity_in_filename).strip().lower()
                    if entity_spaced in query_lower or entity_spaced.replace(' ', '') in query_lower:
                        bonus += 2
                        logger.info(f"   🎯 PASCALCASE match: {filename} entity '{entity_in_filename}' (as '{entity_spaced}') found in query")
                    
                    # Check 3: Fuzzy match (remove all separators)
                    elif entity_in_filename_lower.replace('_', '').replace('-', '') in query_lower.replace(' ', '').replace('_', '').replace('-', ''):
                        bonus += 1
                        logger.info(f"   🎯 FUZZY match: {filename} entity '{entity_in_filename}' fuzzy matched in query")
        
        return bonus
    
    def _generate_pattern_description(self, metadata: Dict[str, Any]) -> str:
        """
        Generate a description for the pattern based on metadata
        """
        parts = []
        
        if metadata.get('purpose'):
            parts.append(metadata['purpose'])
        
        if metadata.get('category'):
            parts.append(f"({metadata['category']})")
        
        if metadata.get('file_path'):
            # ✅ CRITICAL FIX: Handle both Windows (\) and Unix (/) path separators
            import os
            file_name = os.path.basename(metadata['file_path'])
            parts.append(f"from {file_name}")
        
        if not parts:
            parts.append("Code pattern")
        
        return " ".join(parts)
    
    async def get_collection_stats(self, user_id: str) -> Dict[str, Any]:
        """
        Get statistics about the user's code collection
        """
        try:
            collection_name = f"codebase_{user_id}"
            
            try:
                collection = self.chroma_client.get_collection(collection_name)
            except:
                return {
                    'total_patterns': 0,
                    'languages': {},
                    'categories': {}
                }
            
            # Get all documents
            results = collection.get(
                where={"user_id": user_id},
                include=['metadatas']
            )
            
            if not results['metadatas']:
                return {
                    'total_patterns': 0,
                    'languages': {},
                    'categories': {}
                }
            
            # Count by language
            languages = {}
            categories = {}
            
            for metadata in results['metadatas']:
                lang = metadata.get('language', 'unknown')
                cat = metadata.get('category', 'General')
                
                languages[lang] = languages.get(lang, 0) + 1
                categories[cat] = categories.get(cat, 0) + 1
            
            return {
                'total_patterns': len(results['metadatas']),
                'languages': languages,
                'categories': categories
            }
            
        except Exception as e:
            logger.error(f"Error getting collection stats: {str(e)}")
            return {
                'total_patterns': 0,
                'languages': {},
                'categories': {}
            }
