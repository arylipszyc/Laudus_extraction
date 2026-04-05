from services.laudus_service import get_info_API

def fetch_ledger(endpoint, params=None):
    """
    Fetches the accounting ledger records from the Laudus API.
    
    Args:
        endpoint (str): The specific endpoint URL for the ledger records.
        params (dict, optional): Query parameters like dates or account numbers.
        
    Returns:
        dict: The JSON response containing the ledger data.
    """
    return get_info_API(endpoint, params)
