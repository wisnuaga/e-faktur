import os
from typing import Dict
from app.services.djp_client import parse_xml_response


def get_mock_djp_data() -> Dict[str, str]:
    """Read mock XML data and return parsed DJP response."""
    
    mock_path = os.path.join(os.path.dirname(__file__), 'mock.xml')
    try:
        with open(mock_path, 'r') as f:
            mock_xml = f.read()
        return parse_xml_response(mock_xml)
    except FileNotFoundError:
        raise ValueError("Mock data file not found")
    except Exception as e:
        raise ValueError(f"Error reading mock data: {str(e)}")
