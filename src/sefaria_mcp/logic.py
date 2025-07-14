import datetime
import requests
import json
import urllib.parse
import hdate
import base64
from io import BytesIO
from PIL import Image
from typing import Callable, Any
import os
from dotenv import load_dotenv

load_dotenv()
SEFARIA_API_BASE_URL = os.getenv("SEFARIA_API_BASE_URL", "https://www.sefaria.org")

virtual_havruta_host = os.getenv("VIRTUAL_HAVRUTA_HTTP_SERVICE_HOST")
virtual_havruta_port = os.getenv("VIRTUAL_HAVRUTA_HTTP_SERVICE_PORT")

if virtual_havruta_host and virtual_havruta_port:
    SEFARIA_AI_BASE_URL = f"http://{virtual_havruta_host}:{virtual_havruta_port}"
else:
    SEFARIA_AI_BASE_URL = os.getenv("SEFARIA_AI_BASE_URL", "https://ai.sefaria.org")


# Maximum image size in bytes (1MB)
MAX_IMAGE_SIZE = 1024 * 1024

lexicon_map = {
    "Reference/Dictionary/Jastrow" : 'Jastrow Dictionary',
    "Reference/Dictionary/Klein Dictionary" : 'Klein Dictionary',
    "Reference/Dictionary/BDB" : 'BDB Dictionary',
    "Reference/Dictionary/BDB Aramaic" : 'BDB Aramaic Dictionary',
    "Reference/Encyclopedic Works/Kovetz Yesodot VaChakirot" : 'Kovetz Yesodot VaChakirot'
    # Krupnik
}
lexicon_names = list(lexicon_map.values())
lexicon_search_filters = list(lexicon_map.keys())


def get_request_json_data(endpoint, ref=None, param=None):
    """
    Helper function to make GET requests to the Sefaria API and parse the JSON response.
    """
    url = f"{SEFARIA_API_BASE_URL}/{endpoint}"

    if ref:
        url += f"{ref}"

    if param:
        url += f"?{param}"

    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an exception for bad status codes
        data = response.json()
        return data
    except requests.exceptions.RequestException as e:
        print(f"Error during API request: {e}")
        return None

def get_parasha_data():
    """
    Retrieves the weekly Parasha data using the Calendars API.
    """
    data = get_request_json_data("api/calendars")

    if data:
        calendar_items = data.get('calendar_items', [])
        for item in calendar_items:
            if item.get('title', {}).get('en') == 'Parashat Hashavua':
                parasha_ref = item.get('ref')
                parasha_name = item.get('displayValue', {}).get('en')
                return parasha_ref, parasha_name
    
    print("Could not retrieve Parasha data.")
    return None, None

async def get_situational_info(logger):
    """
    Returns situational information related to the Jewish calendar.
    
    Returns:
        str: JSON string containing:
            - Current date in the Gregorian and Hebrew calendars
            - Current year
            - Current Parshat HaShavuah and other daily learning
            - Additional calendar information from Sefaria
    """
    logger = _ensure_logger(logger)
    try:
        # Get current Hebrew date
        # Note: This may be off by a day if server time and user timezone differ
        now = datetime.datetime.now()
        h = hdate.HDateInfo(now)  # Includes day of week
        
        # Get extended calendar information from Sefaria
        # Note: This will retrieve the Israel Parasha when Israel and diaspora differ
        calendar_data = get_request_json_data("api/calendars")
        
        if not calendar_data:
            return json.dumps({
                "error": "Could not retrieve calendar data from Sefaria",
                "Hebrew Date": str(h)
            })
        
        # Add Hebrew date to the response
        calendar_data["Hebrew Date"] = str(h)
        
        return json.dumps(calendar_data, indent=2, ensure_ascii=False)
    
    except Exception as e:
        return json.dumps({
            "error": f"Error retrieving situational information: {str(e)}"
        }, ensure_ascii=False)



async def get_text(logger, reference: str, version_language: str = None) -> str:
    logger = _ensure_logger(logger)
    """
    Retrieves the text for a given reference.
    
    Args:
        reference (str): The reference to retrieve (e.g. 'Genesis 1:1' or 'שולחן ערוך אורח חיים סימן א')
        version_language (str, optional): Language version to retrieve. Options:
            - None: returns all versions
            - "source": returns the original source language (usually Hebrew)
            - "english": returns the English translation
            - "both": returns both source and English
    
    Returns:
        str: JSON string containing the text data
    """
    try:
        # Construct the API URL
        url = f"{SEFARIA_API_BASE_URL}/api/v3/texts/{urllib.parse.quote(reference)}"
        params = []
        
        # Add version parameters based on request
        if version_language == "source":
            params.append("version=source")
        elif version_language == "english":
            params.append("version=english")
        elif version_language == "both":
            params.append("version=english&version=source")
        
        if params:
            url += "?" + "&".join(params)
        
        logger.debug(f"Text API request URL: {url}")
        
        # Make the request
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        # Optimize the response for LLM consumption
        optimized_data = _optimize_text_response(data)
        
        return json.dumps(optimized_data, indent=2, ensure_ascii=False)
    
    except requests.exceptions.RequestException as e:
        return f"Error fetching text: {str(e)}"
    except json.JSONDecodeError as e:
        return f"Error parsing response: {str(e)}"


async def _search(logger, query: str, filters=None, size=8):
    """
    Performs a search against the Sefaria API.
    
    Args:
        query (str): The search query string
        filters (str or list, optional): Filters to limit search scope. Can be a string of one filter, 
            or an array of many strings. They must be complete paths to Sefaria categories or texts.
        size (int, optional): Maximum number of results to return. Default is 8.
        
    Returns:
        dict: The raw search results from the Sefaria API
        
    Raises:
        requests.exceptions.RequestException: If there's an error communicating with the API
        json.JSONDecodeError: If the API response cannot be parsed as JSON
    """
    logger = _ensure_logger(logger)
    url = f"{SEFARIA_API_BASE_URL}/api/search-wrapper/es8"

    # If filters is a list, use it as is. If it's not a list, make it a list.
    filter_list = filters if isinstance(filters, list) else [filters] if filters else []
    filter_fields = [None] * len(filter_list)

    payload = {
        "aggs": [],
        "field": "naive_lemmatizer",
        "filter_fields": filter_fields,
        "filters": filter_list,
        "query": query,
        "size": size,
        "slop": 10,
        "sort_fields": [
            "pagesheetrank"
        ],
        "sort_method": "score",
        "sort_reverse": False,
        "sort_score_missing": 0.04,
        "source_proj": True,
        "type": "text"
    }
    headers = {
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()

        logger.debug(f"Sefaria's Search API response: {response.text}")

        # Parse JSON response
        data = response.json()
        return data

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON response: {str(e)}")
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"Error during search API request: {str(e)}")
        raise


async def search_dictionaries(logger, query: str):
    """
    Given a text query, returns textual content of dictionary entries that match the query in any part of their entry.
    
    Args:
        query (str): The search query for dictionary entries
        
    Returns:
        list: A list of dictionary entries with ref, headword, lexicon_name, and text fields
    """
    logger = _ensure_logger(logger)
    try:
        response = await _search(logger, query, filters=lexicon_search_filters)
        
        results = [
            {
                "ref": hit["_source"]["ref"],
                "headword": hit["_source"]["titleVariants"][0],
                "lexicon_name": lexicon_map[hit["_source"]["path"]],
                "text": hit["_source"]["exact"],
            }
            for hit in response["hits"]["hits"]
        ]
        
        logger.debug(f"Dictionary search results count: {len(results)}")
        return results
        
    except Exception as e:
        logger.error(f"Error during dictionary search: {str(e)}")
        raise


async def search_texts(logger, query: str, filters=None, size=10):
    """
    Searches for Jewish texts in the Sefaria library matching the provided query.
    
    Args:
        query (str): The search query string to find in texts
        filters (str or list, optional): Category paths to limit search scope. 
            Can be a string of one filter or an array of many strings.
            Must be valid category paths (e.g. "Tanakh", "Mishnah", "Talmud", "Midrash", 
            "Halakhah", "Kabbalah", "Talmud/Bavli", "Tanakh/Torah", etc.)
        size (int, optional): Maximum number of results to return. Default is 10.

    Returns:
        list: A list of search results, each containing ref, categories, and text_snippet,
        or a string message if no results found
    """
    logger = _ensure_logger(logger)
    try:
        # Perform initial search with filters
        data = await _search(logger, query, filters, size)
        filter_used = filters
        
        # Check if we have no results and filters were provided
        no_results = not (
            "hits" in data and "hits" in data["hits"] and len(data["hits"]["hits"]) > 0
        )
        
        # If no results and filters were provided, try without filters as last resort
        if no_results and filters:
            logger.info("No results with filters. Attempting search without filters.")
            data = await _search(logger, query, None, size)
            filter_used = None

        # Format the results
        filtered_results = []
        
        # Check if we have hits in the response
        if "hits" in data and "hits" in data["hits"]:
            # Get the actual total hits count
            total_hits = data["hits"].get("total", 0)
            # Handle different response formats
            if isinstance(total_hits, dict) and "value" in total_hits:
                total_hits = total_hits["value"]
         
            # Process each hit
            for hit in data["hits"]["hits"]:
                filtered_result = {}
                source = hit["_source"]
                filtered_result["ref"] = source.get("ref","")
                filtered_result["categories"] = source.get("categories",[])

                # Add info about the filter correction for transparency
                if filter_used != filters and filters:
                    filtered_result["original_filter"] = filters
                    if filter_used is None:
                        filtered_result["filter_correction"] = "Removed filters due to no results"

                text_snippet = ""
                
                # Get highlighted text if available (this contains the search term highlighted)
                if "highlight" in hit:
                    for field_name, highlights in hit["highlight"].items():
                        if highlights and len(highlights) > 0:
                            # Join multiple highlights with ellipses
                            text_snippet = " [...] ".join(highlights)
                            break
                
                # If no highlight, use content from the source
                if not text_snippet:
                    # Try different fields that might contain content
                    for field_name in ["naive_lemmatizer", "exact"]:
                        if field_name in source and source[field_name]:
                            content = source[field_name]
                            if isinstance(content, str):
                                # Limit to a reasonable snippet length
                                text_snippet = content[:300] + ("..." if len(content) > 300 else "")
                                break

                filtered_result["text_snippet"] = text_snippet
                filtered_results.append(filtered_result)

        # Return empty list if no results were found
        if len(filtered_results) == 0:
            logger.debug(f"No results found for '{query}'")
            return []
        
        logger.debug(f"filtered results: {filtered_results}")
        return filtered_results

    except Exception as e:
        logger.error(f"Error during search: {str(e)}")
        return f"Error during search: {str(e)}"


async def search_in_book(logger, query: str, book_name: str, size=10):
    """
    Searches for content within a specific book in the Sefaria library.
    
    Args:
        query (str): The search query string to find in texts
        book_name (str): The name of the book to search within (e.g. "Genesis", "Bereishit Rabbah")
        size (int, optional): Maximum number of results to return. Default is 10.

    Returns:
        list: A list of search results, each containing ref, categories, and text_snippet,
        or a string message if no results found
    """
    logger = _ensure_logger(logger)
    try:
        # Convert book name to filter path
        filter_path = await get_search_path_filter(logger, book_name)
        if not filter_path:
            return f"Could not find valid filter path for book '{book_name}'"
            
        # Use the standard search_texts function with the converted filter path
        return await search_texts(logger, query, filter_path, size)
        
    except Exception as e:
        logger.error(f"Error during book search: {str(e)}")
        return f"Error during book search: {str(e)}"


async def get_name(logger, name: str, limit: int = None, type_filter: str = None) -> str:
    """
    Get autocomplete information for a name from Sefaria's name API.
    
    Args:
        name (str): The text string to match against Sefaria's data collections
        limit (int, optional): Number of results to return (0 indicates no limit)
        type_filter (str, optional): Filter results to a specific type (ref, Collection, Topic, etc.)
        
    Returns:
        str: JSON response from the name API
    """
    logger = _ensure_logger(logger)
    try:
        # URL encode the name
        encoded_name = urllib.parse.quote(name)
        
        # Build the URL with parameters
        url = f"{SEFARIA_API_BASE_URL}/api/name/{encoded_name}"
        params = []
        
        if limit is not None:
            params.append(f"limit={limit}")
            
        if type_filter is not None:
            params.append(f"type={type_filter}")
            
        if params:
            url += "?" + "&".join(params)
            
        logger.debug(f"Name API request URL: {url}")
        
        # Make the request
        response = requests.get(url)
        response.raise_for_status()
        
        # Parse the response
        data = response.json()
        logger.debug(f"Name API response: {json.dumps(data, ensure_ascii=False)}")
        
        # Return the raw JSON data
        return json.dumps(data, indent=2, ensure_ascii=False)
    
    except json.JSONDecodeError as e:
        return f"Error: Failed to parse JSON response: {str(e)}"
    except requests.exceptions.RequestException as e:
        return f"Error during name API request: {str(e)}"

async def get_links(logger, reference: str, with_text: str = "0") -> str:
    """
    Get links (connections) for a given textual reference.
    
    Args:
        reference (str): A valid Sefaria textual reference
        with_text (str, optional): Include the text content of linked resources. 
            Options: "0" (exclude text, default) or "1" (include text).
            Note: Individual texts can be loaded using the texts endpoint.
            
    Returns:
        str: JSON string containing links data
    """
    logger = _ensure_logger(logger)

    if not reference:
        return f"No reference provided"
    
    try:
        # URL encode the reference
        encoded_reference = urllib.parse.quote(reference)
        
        # Build the URL with parameters
        url = f"{SEFARIA_API_BASE_URL}/api/links/{encoded_reference}"
        params = [f"with_text={with_text}"]
            
        if params:
            url += "?" + "&".join(params)
            
        logger.debug(f"Links API request URL: {url}")
        
        # Make the request
        response = requests.get(url)
        response.raise_for_status()
        
        # Parse the response
        data = response.json()
        logger.debug(f"Links API response: {json.dumps(data, ensure_ascii=False)}")
        
        # Optimize the response for LLM consumption
        optimized_data = _optimize_links_response(data)
        
        # Return the optimized JSON data
        return json.dumps(optimized_data, indent=2, ensure_ascii=False)
    
    except json.JSONDecodeError as e:
        return f"Error: Failed to parse JSON response: {str(e)}"
    except requests.exceptions.RequestException as e:
        return f"Error during links API request: {str(e)}"

async def get_shape(logger, name: str) -> str:
    """
    Get the shape (structure) of a text or list texts in a category/corpus.
    
    Args:
        name (str): Either a text name (e.g., "Genesis") or a category/corpus name 
            (e.g., "Tanakh", "Mishnah", "Talmud", "Midrash", "Halakhah", "Kabbalah", 
            "Liturgy", "Jewish Thought", "Tosefta", "Chasidut", "Musar", "Responsa", 
            "Reference", "Second Temple", "Yerushalmi", "Midrash Rabbah", "Bavli")
            
    Returns:
        str: JSON string containing shape data for the text or category
    """
    logger = _ensure_logger(logger)
    try:
        # URL encode the name
        encoded_name = urllib.parse.quote(name)
        
        # Build the URL
        url = f"{SEFARIA_API_BASE_URL}/api/shape/{encoded_name}"
            
        logger.debug(f"Shape API request URL: {url}")
        
        # Make the request
        response = requests.get(url)
        response.raise_for_status()
        
        # Parse the response
        data = response.json()
        logger.debug(f"Shape API response: {json.dumps(data, ensure_ascii=False)}")
        
        # Return the raw JSON data
        return json.dumps(data, indent=2, ensure_ascii=False)
    
    except json.JSONDecodeError as e:
        return f"Error: Failed to parse JSON response: {str(e)}"
    except requests.exceptions.RequestException as e:
        return f"Error during shape API request: {str(e)}"

async def get_english_translations(logger, reference: str) -> str:
    """
    Retrieves all English translations for a given textual reference.
    
    Args:
        reference (str): The reference to retrieve translations for (e.g. 'Genesis 1:1' or 'שולחן ערוך אורח חיים סימן א')
        
    Returns:
        str: JSON string containing all English translations with just the version title and text
    """
    logger = _ensure_logger(logger)
    try:
        # Construct the API URL with the version=english|all parameter
        url = f"{SEFARIA_API_BASE_URL}/api/v3/texts/{urllib.parse.quote(reference)}?version=english|all"
        
        logger.debug(f"English translations API request URL: {url}")
        
        # Make the request
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        # Extract only version title and text from each English version
        simplified_translations = []
        
        if "versions" in data:
            for version in data["versions"]:
                simplified_translation = {
                    "versionTitle": version.get("versionTitle", ""),
                    "text": version.get("text", "")
                }
                simplified_translations.append(simplified_translation)
        
        result = {
            "reference": reference,
            "englishTranslations": simplified_translations
        }
        
        return json.dumps(result, indent=2, ensure_ascii=False)
    
    except requests.exceptions.RequestException as e:
        return f"Error fetching translations: {str(e)}"
    except json.JSONDecodeError as e:
        return f"Error parsing response: {str(e)}"


async def get_index(logger, title: str) -> str:
    """
    Retrieves the index (bibliographic record) for a given text.
    
    Args:
        title (str): The title of the text to retrieve the index for (e.g. 'Genesis', 'Mishnah', 'Talmud')
        
    Returns:
        str: JSON string containing the index data for the text
    """
    logger = _ensure_logger(logger)
    try:
        # URL encode the title
        encoded_title = urllib.parse.quote(title)
        
        # Build the URL
        url = f"{SEFARIA_API_BASE_URL}/api/v2/raw/index/{encoded_title}"
            
        logger.debug(f"Index API request URL: {url}")
        
        # Make the request
        response = requests.get(url)
        response.raise_for_status()
        
        # Parse the response
        data = response.json()
        logger.debug(f"Index API response: {json.dumps(data, ensure_ascii=False)}")
        
        # Optimize the response for LLM consumption
        optimized_data = _optimize_index_response(data)
        
        # Return the optimized JSON data
        return json.dumps(optimized_data, indent=2, ensure_ascii=False)
    
    except json.JSONDecodeError as e:
        return f"Error: Failed to parse JSON response: {str(e)}"
    except requests.exceptions.RequestException as e:
        return f"Error during index API request: {str(e)}"

async def get_topics(logger, topic_slug: str, with_links: bool = False, with_refs: bool = False) -> str:
    """
    Retrieves detailed information about a specific topic from Sefaria's topic system.
    
    Args:
        topic_slug (str): The slug identifier for the topic (e.g. 'moses', 'sabbath', 'torah')
        with_links (bool, optional): Include related topic links. Default is False.
        with_refs (bool, optional): Include text references tagged with this topic. Default is False.
        
    Returns:
        str: JSON string containing topic metadata, description, and optionally links/references
    """
    logger = _ensure_logger(logger)
    try:
        if not topic_slug:
            return f"No topic slug provided"
        
        # URL encode the topic slug
        encoded_slug = urllib.parse.quote(topic_slug)
        
        # Build the URL with parameters
        url = f"{SEFARIA_API_BASE_URL}/api/v2/topics/{encoded_slug}"
        params = []
        
        if with_links:
            params.append("with_links=1")
        if with_refs:
            params.append("with_refs=1")
            
        if params:
            url += "?" + "&".join(params)
            
        logger.debug(f"Topics API request URL: {url}")
        
        # Make the request
        response = requests.get(url)
        response.raise_for_status()
        
        # Parse the response
        data = response.json()
        logger.debug(f"Topics API response: {json.dumps(data, ensure_ascii=False)}")
        
        # Optimize the response for LLM consumption
        optimized_data = _optimize_topics_response(data)
        
        # Return the optimized JSON data
        return json.dumps(optimized_data, indent=2, ensure_ascii=False)
    
    except json.JSONDecodeError as e:
        return f"Error: Failed to parse JSON response: {str(e)}"
    except requests.exceptions.RequestException as e:
        return f"Error during topics API request: {str(e)}"

async def get_manuscript_info(logger, reference: str) -> str:
    """
    Retrieves manuscript images and metadata for a given textual reference.
    
    Args:
        reference (str): A valid Sefaria textual reference (e.g. 'Genesis 1:1', 'Berakhot 2a')
        
    Returns:
        str: JSON string containing manuscript data including image URLs, or error message if no manuscripts found
    """
    logger = _ensure_logger(logger)
    try:
        # URL encode the reference
        encoded_reference = urllib.parse.quote(reference)
        
        # Build the URL
        url = f"{SEFARIA_API_BASE_URL}/api/manuscripts/{encoded_reference}"
            
        logger.debug(f"Manuscripts API request URL: {url}")
        
        # Make the request
        response = requests.get(url)
        response.raise_for_status()
        
        # Parse the response
        data = response.json()
        logger.debug(f"Manuscripts API response: {json.dumps(data, ensure_ascii=False)}")
        
        # Check if any manuscripts were found
        if not data or len(data) == 0:
            return f"No manuscripts found for reference '{reference}'"
        
        # Return the raw JSON data
        return json.dumps(data, indent=2, ensure_ascii=False)
    
    except json.JSONDecodeError as e:
        return f"Error: Failed to parse JSON response: {str(e)}"
    except requests.exceptions.RequestException as e:
        return f"Error during manuscripts API request: {str(e)}"

async def get_manuscript(logger, image_url: str, manuscript_title: str = None) -> dict:
    """
    Downloads a manuscript image from the provided URL and returns it as base64 data.
    If the image is larger than MAX_IMAGE_SIZE, it will be resized while maintaining aspect ratio.
    
    Args:
        image_url (str): The URL of the manuscript image to download
        manuscript_title (str, optional): Title/description for the manuscript for display purposes
        
    Returns:
        dict: Dictionary containing the image data and metadata for MCP response
    """
    logger = _ensure_logger(logger)
    try:
        logger.debug(f"Downloading manuscript image from: {image_url}")
        
        # Download the image
        response = requests.get(image_url, timeout=30)
        response.raise_for_status()
        
        # Get the content type to determine the MIME type
        content_type = response.headers.get('content-type', 'image/jpeg')
        if not content_type.startswith('image/'):
            content_type = 'image/jpeg'  # Default fallback
        
        original_size = len(response.content)
        image_data = response.content
        was_resized = False
        
        # Check if image needs to be resized
        if original_size > MAX_IMAGE_SIZE:
            logger.debug(f"Image size {original_size} bytes exceeds limit of {MAX_IMAGE_SIZE} bytes, resizing...")
            
            try:
                # Open image with PIL
                image = Image.open(BytesIO(response.content))
                
                # Calculate resize factor to get under MAX_IMAGE_SIZE
                # We'll use an iterative approach since compressed size is hard to predict
                resize_factor = 0.8  # Start with 80% of original size
                max_attempts = 5
                attempts = 0
                
                while attempts < max_attempts:
                    # Calculate new dimensions
                    new_width = int(image.width * resize_factor)
                    new_height = int(image.height * resize_factor)
                    
                    # Resize image maintaining aspect ratio
                    resized_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    
                    # Convert back to bytes
                    output_buffer = BytesIO()
                    
                    # Determine format for saving
                    save_format = 'JPEG'
                    if content_type == 'image/png':
                        save_format = 'PNG'
                    elif content_type == 'image/webp':
                        save_format = 'WEBP'
                    
                    # Save with quality optimization for JPEG
                    if save_format == 'JPEG':
                        resized_image.save(output_buffer, format=save_format, quality=85, optimize=True)
                    else:
                        resized_image.save(output_buffer, format=save_format, optimize=True)
                    
                    image_data = output_buffer.getvalue()
                    new_size = len(image_data)
                    
                    logger.debug(f"Resize attempt {attempts + 1}: {new_width}x{new_height}, size: {new_size} bytes")
                    
                    if new_size <= MAX_IMAGE_SIZE:
                        was_resized = True
                        logger.debug(f"Successfully resized image from {original_size} to {new_size} bytes")
                        break
                    
                    # Reduce resize factor for next attempt
                    resize_factor *= 0.8
                    attempts += 1
                
                if attempts >= max_attempts:
                    logger.warning(f"Could not resize image below {MAX_IMAGE_SIZE} bytes after {max_attempts} attempts")
                    # Fall back to original image
                    image_data = response.content
                    
            except Exception as resize_error:
                logger.error(f"Error during image resize: {str(resize_error)}")
                # Fall back to original image
                image_data = response.content
        
        # Convert to base64
        base64_data = base64.b64encode(image_data).decode('utf-8')
        final_size = len(image_data)
        
        logger.debug(f"Successfully processed manuscript image, final size: {final_size} bytes")
        
        # Extract filename from URL for display
        filename = image_url.split('/')[-1]
        if not filename or '.' not in filename:
            filename = "manuscript.jpg"
        
        title = manuscript_title or f"Manuscript: {filename}"
        if was_resized:
            title += f" (resized from {original_size:,} to {final_size:,} bytes)"
        
        return {
            "success": True,
            "image_data": base64_data,
            "mime_type": content_type,
            "size": final_size,
            "original_size": original_size,
            "was_resized": was_resized,
            "filename": filename,
            "title": title,
            "source_url": image_url
        }
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Error downloading manuscript image: {str(e)}")
        return {
            "success": False,
            "error": f"Error downloading manuscript image: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Error processing manuscript image: {str(e)}")
        return {
            "success": False,
            "error": f"Error processing manuscript image: {str(e)}"
        }

async def get_search_path_filter(logger, book_name: str) -> str:
    """
    Converts a book name into a valid search filter path using Sefaria's search-path-filter API.
    
    Args:
        book_name (str): The name of the book to convert to a search filter path
        
    Returns:
        str: The search filter path string, or None if the conversion failed
    """
    logger = _ensure_logger(logger)
    try:
        # URL encode the book name
        encoded_name = urllib.parse.quote(book_name)
        
        # Build the URL
        url = f"{SEFARIA_API_BASE_URL}/api/search-path-filter/{encoded_name}"
            
        logger.debug(f"Search path filter API request URL: {url}")
        
        # Make the request
        response = requests.get(url)
        response.raise_for_status()
        
        # The response is just a string, not JSON
        filter_path = response.text.strip()
        logger.debug(f"Search path filter response: {filter_path}")
        
        return filter_path
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Error during search path filter API request: {str(e)}")
        return None

async def knn_search(logger, query: str, filters: dict = None) -> str:
    """
    Performs KNN search on embeddings of texts from Sefaria using the AI server.
    
    Args:
        query (str): The search query to find similar text chunks
        filters (dict, optional): Metadata filters to apply to the search
        
    Returns:
        str: JSON string containing the nearest chunks with their original content and metadata
    """
    logger = _ensure_logger(logger)
    try:
        # Build the URL for the KNN search endpoint
        url = f"{SEFARIA_AI_BASE_URL}/api/knn-search"
        
        # Prepare the request payload
        payload = {
            "query": query
        }
        
        # Add filters if provided
        if filters:
            payload["filters"] = filters
        
        logger.debug(f"KNN search API request URL: {url}")
        logger.debug(f"KNN search payload: {payload}")
        
        # Make the POST request
        response = requests.post(url, json=payload)
        response.raise_for_status()
        
        # Parse the JSON response
        data = response.json()
        logger.debug(f"KNN search response received, size: {len(str(data))} characters")
        
        return json.dumps(data, indent=2, ensure_ascii=False)
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error during KNN search API request: {str(e)}")
        return json.dumps({
            "error": f"Error during KNN search API request: {str(e)}"
        }, ensure_ascii=False)
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing KNN search response: {str(e)}")
        return json.dumps({
            "error": f"Error parsing KNN search response: {str(e)}"
        }, ensure_ascii=False) 

# ---------------------------------------------------------------------------
# Logger adapter utilities
# ---------------------------------------------------------------------------


def _ensure_logger(logger: Any):
    """Normalise the *logger* argument so that calls like ``logger.debug(...)``
    work whether the value passed in is a standard ``logging.Logger`` instance
    *or* the callable ``ctx.log`` provided by FastMCP.

    FastMCP's ``ctx.log`` is a simple function – it has no *debug/info/error*
    attributes.  To keep the rest of this module agnostic we attach these
    attributes at runtime when necessary, pointing them back to the original
    callable.  In this way the rest of the codebase can assume a traditional
    logging interface while still supporting FastMCP's simplified logger.
    """
    # If the supplied object already behaves like a logger, leave it untouched.
    if hasattr(logger, "debug") and callable(logger.debug):
        return logger

    # If we were given a bare callable (e.g. ``ctx.log``) we cannot attach
    # attributes directly when it is a *method* object (they are immutable).
    # Instead we wrap it in a lightweight adapter that provides the usual
    # logging API while delegating everything to the original callable.

    if callable(logger):

        class _CallableLogger:  # pragma: no cover – simple delegate
            def __init__(self, cb):
                self._cb = cb

            # Internal helper to mirror logs to server stdout
            def _emit_stdout(self, level: str, *args, **kwargs):  # noqa: D401 – simple helper
                if args:
                    # If first arg is format string with %s style, rely on logging style simplicity
                    message = args[0]
                    # Handle old-style % formatting if extra args provided
                    if len(args) > 1 and isinstance(message, str) and "%" in message:
                        try:
                            message = message % args[1:]
                        except Exception:
                            message = " ".join(str(a) for a in args)
                else:
                    message = ""
                print(f"[{level}] {message}")

            # Allow ``adapter("message")`` as a synonym for ``adapter.debug``
            def __call__(self, *args, **kwargs):
                self._cb(*args, **kwargs)

            # Mirror each log level to ctx.log and stdout
            def debug(self, *args, **kwargs):
                self._cb(*args, **kwargs)
                self._emit_stdout("DEBUG", *args, **kwargs)

            info = warning = error = debug  # All levels map to same callable

        return _CallableLogger(logger)

    # As a final fallback, silently replace *logger* with ``print`` so that we
    # do not raise further attribute-errors.  This should never normally
    # happen but provides a safe default in mis-configuration scenarios.
    def _print_logger(message: str):  # pragma: no cover
        print(message)

    class _PrintLogger:
        def __call__(self, msg):
            print(msg)

        debug = info = warning = error = __call__  # type: ignore[attr-defined]

    return _PrintLogger() 

def _optimize_text_response(data):
    """Optimize text response for LLM consumption by removing unnecessary fields"""
    if not isinstance(data, dict):
        return data
        
    # Keep only essential fields for text data
    essential_fields = {
        'ref', 'versions', 'available_versions', 'requestedRef', 'spanningRefs',
        'textType', 'sectionRef', 'he', 'text', 'primary_title'
    }
    
    optimized = {k: v for k, v in data.items() if k in essential_fields}
    
    # Simplify versions array - keep only essential version info
    if 'versions' in optimized:
        simplified_versions = []
        for version in optimized['versions']:
            if isinstance(version, dict):
                simplified_version = {
                    'text': version.get('text', ''),
                    'versionTitle': version.get('versionTitle', ''),
                    'languageFamilyName': version.get('languageFamilyName', ''),
                    'versionSource': version.get('versionSource', '')
                }
                simplified_versions.append(simplified_version)
        optimized['versions'] = simplified_versions
    
    # Simplify available_versions
    if 'available_versions' in optimized:
        simplified_available = []
        for version in optimized['available_versions']:
            if isinstance(version, dict):
                simplified_version = {
                    'versionTitle': version.get('versionTitle', ''),
                    'languageFamilyName': version.get('languageFamilyName', '')
                }
                simplified_available.append(simplified_version)
        optimized['available_versions'] = simplified_available
        
    return optimized

def _optimize_links_response(data):
    """Optimize links response for LLM consumption"""
    if not isinstance(data, list):
        return data
        
    optimized_links = []
    for link in data:
        if isinstance(link, dict):
            # Keep only essential link fields
            optimized_link = {
                'ref': link.get('ref', ''),
                'sourceRef': link.get('sourceRef', ''),
                'anchorText': link.get('anchorText', ''),
                'type': link.get('type', ''),
                'category': link.get('category', '')
            }
            # Include text if available and not too long
            if 'text' in link and isinstance(link['text'], str):
                if len(link['text']) < 500:  # Limit text length
                    optimized_link['text'] = link['text']
                else:
                    optimized_link['text'] = link['text'][:500] + '...'
            optimized_links.append(optimized_link)
            
    return optimized_links

def _optimize_topics_response(data):
    """Optimize topics response for LLM consumption by removing huge refs arrays"""
    if not isinstance(data, dict):
        return data
        
    # Keep essential topic information but remove/limit large arrays
    essential_fields = {
        'slug', 'titles', 'description', 'categoryDescription', 'numSources',
        'primaryTitle', 'image', 'good_to_promote'
    }
    
    optimized = {k: v for k, v in data.items() if k in essential_fields}
    
    # Limit links to first 10 if present
    if 'links' in data and isinstance(data['links'], list):
        optimized['links'] = data['links'][:10]
        
    # Severely limit refs to first 10 to prevent massive responses
    if 'refs' in data and isinstance(data['refs'], list):
        optimized['refs'] = data['refs'][:10]
        optimized['refs_note'] = f"Showing first 10 of {len(data['refs'])} total refs"
        
    return optimized

def _optimize_index_response(data):
    """Optimize index response for LLM consumption"""
    if not isinstance(data, dict):
        return data
        
    # Keep essential bibliographic fields
    essential_fields = {
        'title', 'heTitle', 'titleVariants', 'schema', 'categories',
        'sectionNames', 'addressTypes', 'length', 'lengths',
        'textDepth', 'primaryTitle', 'compDate', 'era', 'authors'
    }
    
    optimized = {k: v for k, v in data.items() if k in essential_fields}
    
    return optimized 