from pipeline.services.laudus_service import get_info_API

def fetch_ledger(endpoint, params=None, book=None):
    """
    Fetches the accounting ledger records from the Laudus API.

    Args:
        endpoint (str): The specific endpoint URL for the ledger records.
        params (dict, optional): Query parameters like dates or account numbers.
        book (BookConfig, optional): Libro Laudus (Story 12.2). None = EAG legacy.

    Returns:
        dict: The JSON response containing the ledger data.
    """
    return get_info_API(endpoint, params, book=book)
