import json
from typing import Dict, Any, List

class ModelOutputInvalid(Exception):
    pass

class ModelResultValidator:
    """Validates output schemas for model inferences."""
    
    @staticmethod
    def validate_document_classification(output_text: str) -> Dict[str, Any]:
        """
        Validates the output of a document.classify execution.
        Must conform to:
        {
          "class": "...",
          "confidence": 0.0,
          "reason_codes": []
        }
        """
        try:
            data = json.loads(output_text)
        except json.JSONDecodeError as e:
            raise ModelOutputInvalid(f"Output is not valid JSON: {e}")
            
        if not isinstance(data, dict):
            raise ModelOutputInvalid("Output must be a JSON object")
            
        required_fields = {"class", "confidence", "reason_codes"}
        if not required_fields.issubset(data.keys()):
            missing = required_fields - set(data.keys())
            raise ModelOutputInvalid(f"Missing required fields: {missing}")
            
        cls = data["class"]
        if not isinstance(cls, str):
            raise ModelOutputInvalid("'class' must be a string")
            
        allowed_classes = {"confidential", "public", "internal", "restricted"}
        if cls not in allowed_classes:
            raise ModelOutputInvalid(f"'class' must be one of {allowed_classes}")
            
        conf = data["confidence"]
        if not isinstance(conf, (int, float)):
            raise ModelOutputInvalid("'confidence' must be a number")
        if not (0.0 <= conf <= 1.0):
            raise ModelOutputInvalid("'confidence' must be between 0.0 and 1.0")
            
        reasons = data["reason_codes"]
        if not isinstance(reasons, list):
            raise ModelOutputInvalid("'reason_codes' must be a list")
            
        return data
