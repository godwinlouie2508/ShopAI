# modules/shopping.py

import streamlit as st
import requests
import openai
import re
from urllib.parse import urlparse
from typing import List, Dict, Optional
from config import SERP_API_KEY, OPENAI_KEY
from modules.utils import get_site_domains, get_primary_domain # <-- Add get_primary_domain here

# Use Streamlit secrets if deployed, otherwise use local config file
if hasattr(st, 'secrets'):
    SERP_API_KEY = st.secrets["SERP_API_KEY"]
    OPENAI_KEY = st.secrets["OPENAI_KEY"]
else:
    from config import SERP_API_KEY, OPENAI_KEY

from modules.utils import get_site_domains, get_primary_domain

# --- SEARCH OPTIMIZATION ---

def clean_search_query(query: str) -> str:
    """Cleans and normalizes the search query."""
    cleaned = re.sub(r'\s+', ' ', query.strip())
    replacements = {
        "macbook pro": "MacBook Pro", "macbook air": "MacBook Air",
        "iphone": "iPhone", "ipad": "iPad",
    }
    for old, new in replacements.items():
        cleaned = re.sub(rf'\b{old}\b', new, cleaned, flags=re.IGNORECASE)
    return cleaned

# def optimize_query_for_google_shopping(item_name: str, site_preference: str) -> str:
#     """Optimizes the search query for Google Shopping."""
#     cleaned_query = clean_search_query(item_name)
#     modifiers = []
#     if "new" not in cleaned_query.lower():
#         modifiers.append("new")
#     if site_preference.lower() != "any":
#         modifiers.append(site_preference)
#     return " ".join([cleaned_query] + modifiers)


def optimize_query_for_google_shopping(item_name: str, site_preference: str) -> str:
    """Optimizes the query by adding keywords, NOT a strict site: filter."""
    cleaned_query = clean_search_query(item_name)

    optimized_parts = [cleaned_query]

    if "new" not in cleaned_query.lower():
        optimized_parts.append("new")

    # Add the retailer name as a keyword to bias the search
    if site_preference.lower() != "any":
        optimized_parts.append(site_preference)

    return " ".join(optimized_parts)


def perform_search(search_query: str, site_preference: str, num_results: int = 50) -> List[Dict]:
    """Performs the search on SerpApi, simplifying params for site-specific queries."""
    optimized_query = optimize_query_for_google_shopping(search_query, site_preference)

    # Base parameters for all searches
    params = {
        "engine": "google_shopping",
        "q": optimized_query,
        "gl": "us",
        "hl": "en",
        "num": num_results,
        "api_key": SERP_API_KEY,
        "tbm": "shop",
    }

    # IMPORTANT: Only add the 'tbs' parameter for general "Any" retailer searches.
    # For site-specific searches, the 'site:' operator in the query is sufficient.
    if site_preference.lower() == "any":
        params["tbs"] = "p_ord:p,mr:1,merchagg:g"

    try:
        resp = requests.get("https://serpapi.com/search.json", params=params)
        resp.raise_for_status()
        results = resp.json().get("shopping_results", [])

        # Only show the initial count; subsequent filtering stats are shown later
        if st.session_state.get("show_initial_count", True):
            st.info(f"🔍 Found {len(results)} initial results for '{search_query}' from the API.")
            st.session_state.show_initial_count = False  # Show only once per search

        return results
    except requests.exceptions.RequestException as e:
        st.error(f"Error performing search: {e}")
        return []


# --- FILTERING LOGIC ---

def remove_duplicates(results: List[Dict]) -> List[Dict]:
    """Removes duplicate products based on ID and normalized title."""
    seen_ids, seen_titles, unique_results = set(), set(), []
    for result in results:
        product_id = result.get("product_id") or result.get("id") or result.get("link", "")
        title = result.get("title", "").lower().strip()
        normalized_title = re.sub(r'\s+', ' ', title).strip()
        if product_id not in seen_ids and normalized_title not in seen_titles:
            seen_ids.add(product_id)
            seen_titles.add(normalized_title)
            unique_results.append(result)
    return unique_results


def is_accessory_or_irrelevant(title: str, item: str) -> bool:
    """Checks if a product is an accessory or obviously irrelevant."""
    accessory_keywords = ["case", "cover", "skin", "screen protector", "charger", "cable", "adapter", "stand", "mount",
                          "sleeve", "bag", "keyboard", "mouse", "dock", "hub", "sticker", "decal", "film", "guard",
                          "protector", "holder", "grip", "cleaning", "cloth", "kit", "tool", "repair",
                          "replacement part"]
    for keyword in accessory_keywords:
        if keyword in title and keyword not in item.lower():
            return True
    return False


def is_used_or_refurbished(product: Dict, title: str) -> bool:
    """Checks for indicators of a used or refurbished product."""
    if 'second_hand_condition' in product:
        return True
    used_keywords = ["used", "refurbished", "renewed", "pre-owned", "open box", "grade b", "grade c", "scratched"]
    return any(keyword in title for keyword in used_keywords)


def is_from_correct_site(product: Dict, site_pref: str) -> bool:
    """
    Stricter site verification that relies only on the source and domain.
    """
    if site_pref.lower() == "any":
        return True

    site_pref_cleaned = site_pref.lower().replace(" ", "")

    # 1. Check the 'source' field (most reliable check)
    source = product.get("source", "").lower().replace(" ", "")
    if site_pref_cleaned in source:
        return True

    # 2. Check the actual domain of the link (second most reliable check)
    link = product.get("link", "")
    if link:
        try:
            # We ONLY check the parsed domain, not the entire link string.
            domain = urlparse(link).netloc.lower()
            target_domains = get_site_domains(site_pref)
            if any(target_domain in domain for target_domain in target_domains):
                return True
        except Exception:
            # If parsing fails, we can't validate the domain.
            pass

    # If neither of the reliable checks pass, it's from the wrong site.
    return False


def is_price_reasonable(price: float, item: str) -> bool:
    """Checks if a product's price is within a reasonable range for its category."""
    item_lower = item.lower()
    price_ranges = {
        "macbook": (500, 5000), "iphone": (200, 2000), "ipad": (200, 2000),
        "laptop": (300, 5000), "tv": (150, 5000), "tablet": (100, 2000)
    }
    for category, (min_price, max_price) in price_ranges.items():
        if category in item_lower:
            return min_price <= price <= max_price
    return 1 <= price <= 10000


def is_semantically_relevant(title: str, item: str) -> bool:
    """
    Checks if the core concepts of the search item are present in the title.
    This prevents completely unrelated items from being included.
    """
    # Find all words in the search item and product title
    item_words = set(re.findall(r'\b\w+\b', item.lower()))
    title_words = set(re.findall(r'\b\w+\b', title.lower()))

    # Define common words that don't carry much meaning
    stop_words = {'a', 'an', 'the', 'and', 'for', 'with', 'in', 'on', 'of', 'to', 'new'}

    # Get the essential words from the search item
    core_item_words = item_words - stop_words

    if not core_item_words:
        return True  # If no core words, we can't judge, so we allow it

    # Check if there is any overlap between the core search words and the title words
    return core_item_words.intersection(title_words)


def should_include_product(product: Dict, item: str, site_pref: str) -> bool:
    """
    Master filter function to decide if a product should be included.
    """
    title = product.get("title", "").lower()
    price_str = product.get("price", "")
    if not title or not price_str:
        return False
    try:
        numeric_price = float(price_str.replace("$", "").replace(",", ""))
        if numeric_price <= 0: return False
    except (ValueError, AttributeError):
        return False

    # --- ADDED THIS NEW CHECK ---
    if not is_semantically_relevant(title, item):
        return False

    if is_accessory_or_irrelevant(title, item): return False
    if is_used_or_refurbished(product, title): return False
    if not is_from_correct_site(product, site_pref): return False
    if not is_price_reasonable(numeric_price, item): return False

    return True


def apply_comprehensive_filters(results: List[Dict], item: str, site_pref: str) -> List[Dict]:
    """Applies all filtering rules to a list of products."""
    return [p for p in results if should_include_product(p, item, site_pref)]


# --- SCORING & SORTING ---

def calculate_advanced_relevance_scores(results: List[Dict], item: str) -> List[Dict]:
    """
    Calculates more nuanced relevance scores by incorporating ratings and reviews.
    """
    item_lower = item.lower()
    item_words = set(re.findall(r'\b\w+\b', item_lower))

    for product in results:
        title = product.get("title", "").lower()
        score = 0

        # 1. Base score on word overlap
        common_words = item_words.intersection(set(re.findall(r'\b\w+\b', title)))
        score += len(common_words) * 100

        # 2. Huge bonus for exact phrase match
        if item_lower in title:
            score += 1000

        # 3. Add score based on product rating and review count
        # This rewards popular and well-regarded items.
        rating = product.get('rating', 0)
        reviews = product.get('reviews', 0)
        if isinstance(rating, (int, float)) and isinstance(reviews, int):
            # A 5-star item gets a 100 point bonus. A 4-star gets 80, etc.
            score += rating * 20
            # Add points for having reviews, capping at 150 to avoid overpowering.
            score += min(reviews / 4, 150)

        # 4. Small penalty for overly long or generic titles
        if len(title) > 100:
            score -= 25

        product["relevance_score"] = score
    return results

def sort_results(filtered_results: List[Dict], sort_pref: str, item: str) -> List[Dict]:
    """Sorts results based on user preference."""
    for product in filtered_results:
        try:
            product["numeric_price"] = float(product.get("price", "0").replace("$", "").replace(",", ""))
        except (ValueError, AttributeError):
            product["numeric_price"] = float('inf')

    if sort_pref == "Cheapest":
        return sorted(filtered_results, key=lambda x: x.get("numeric_price", float('inf')))
    elif sort_pref == "Highest Rated" and any('rating' in p for p in filtered_results):
        return sorted(filtered_results, key=lambda x: x.get('rating', 0), reverse=True)
    else:  # "Default" sorting
        scored_results = calculate_advanced_relevance_scores(filtered_results, item)
        return sorted(scored_results,
                      key=lambda x: (-x.get("relevance_score", 0), x.get("numeric_price", float('inf'))))


# --- MASTER FETCH & PROCESS FUNCTION ---

def get_shopping_results(item: str, site_pref: str, sort_pref: str) -> tuple:
    """
    The main orchestrator for fetching, filtering, and sorting products.
    --- FINAL, CLEAN VERSION ---
    """
    raw_results = perform_search(item, site_pref)
    if not raw_results:
        return item, []

    unique_results = remove_duplicates(raw_results)
    filtered_results = apply_comprehensive_filters(unique_results, item, site_pref)
    sorted_results = sort_results(filtered_results, sort_pref, item)

    # Return only the item and the final list of sorted products
    return item, sorted_results[:10]


# --- POST-SELECTION HELPERS ---

def get_enhanced_direct_link(product_choice, site_pref):
    """
    Gets the best possible direct link, intelligently prioritizing the selected retailer.
    """
    # --- Step 1: Check if the link already in the product data is the correct one ---
    if product_choice.get('link'):
        # Our improved is_from_correct_site function can validate this reliably.
        if is_from_correct_site(product_choice, site_pref):
            return product_choice['link']

    # --- Step 2: Fallback - If not, search the detailed product page for all sellers ---
    product_api_id = product_choice.get("product_id") or product_choice.get("id")
    if not product_api_id:
        # If no ID, we can't do a deeper search. Return the original link.
        return product_choice.get('link')

    try:
        # Fetch the detailed seller list from the Google Product API
        params = {
            "engine": "google_product",
            "product_id": product_api_id,
            "api_key": SERP_API_KEY,
            "offers": "1"
        }
        resp = requests.get("https://serpapi.com/search.json", params=params).json()
        online_sellers = resp.get("sellers_results", {}).get("online_sellers", [])

        if online_sellers:
            # --- This is the new, crucial logic ---
            # If a specific retailer is chosen, loop through sellers to find a match.
            if site_pref.lower() != "any":
                target_domains = get_site_domains(site_pref)
                site_pref_cleaned = site_pref.lower().replace(" ", "")

                for seller in online_sellers:
                    seller_name = seller.get("name", "").lower()
                    seller_link = seller.get("link", "")  # Keep original case for urlparse

                    # Check if the seller's name or link domain matches the preference
                    if site_pref_cleaned in seller_name:
                        return seller.get("link")

                    try:
                        seller_domain = urlparse(seller_link).netloc.lower()
                        if any(domain in seller_domain for domain in target_domains):
                            return seller.get("link")  # Return the matching retailer link immediately
                    except Exception:
                        continue  # Ignore parsing errors on weird links

            # If no matching retailer was found, or if preference was "Any", return the top-listed seller.
            return online_sellers[0].get("link")

    except Exception as e:
        st.warning(f"Could not fetch detailed link: {e}")

    # Final fallback: return the original link from the shopping results.
    return product_choice.get('link')

def get_why_explanation(item, chosen_product, all_products):
    """Generates an AI explanation for why a product was chosen."""
    openai.api_key = OPENAI_KEY
    product_info = f"Selected: {chosen_product['title']} - ${chosen_product.get('numeric_price', 0):.2f}"
    alternatives = [f"{p['title']} - ${p.get('numeric_price', 0):.2f}" for p in all_products if p != chosen_product]
    alternatives_text = " | ".join(alternatives) if alternatives else "No alternatives shown"

    try:
        resp = openai.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system",
                 "content": "You are a shopping assistant. Explain in 35-40 words why this product was chosen as the best option based on relevance and price. Be concise."},
                {"role": "user", "content": f"Item needed: {item}\n{product_info}\nAlternatives: {alternatives_text}"}
            ],
            temperature=0.3, max_tokens=60
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        st.warning(f"GPT explanation failed: {e}.")
        return "This product offers a strong combination of relevance and competitive pricing for your search."