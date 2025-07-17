#ShopAI.py

import streamlit as st
import pandas as pd
import openai
import json
from concurrent.futures import ThreadPoolExecutor

# Import from our new modules
from modules import ui, state, utils, shopping
if hasattr(st, 'secrets'):
    OPENAI_KEY = st.secrets["OPENAI_KEY"]
else:
    from config import OPENAI_KEY

# --- 1. PAGE SETUP & INITIALIZATION ---
ui.setup_page()
ui.display_sidebar()
state.initialize_state()

# --- 2. MAIN LAYOUT (CENTER & RIGHT COLUMNS) ---
center_col, right_col = st.columns([2.2, 1.3])

with center_col:
    st.markdown('<div class="scrollable-column">', unsafe_allow_html=True)
    st.title("Agentic AI for Shopping")
    st.caption("Upload your list or chat with AI to start shopping smarter.")

    # --- 3. MODE SELECTION & STATE RESET ---
    st.session_state.mode = st.radio(
        "Start by:", ["Upload Image", "Chat with AI"],
        index=["Upload Image", "Chat with AI"].index(st.session_state.mode_last), key="mode_selector"
    )
    state.reset_state_on_mode_change()

    # --- 4. ITEM EXTRACTION (OCR or CHAT) ---
    extracted = []
    if st.session_state.mode == "Upload Image":
        img = st.file_uploader("Upload your handwritten list", type=["jpg", "png", "jpeg", "webp"])
        if img:
            with st.spinner("🔍 Extracting text from image..."):
                ocr_raw = utils.extract_text_from_image(img)

            if ocr_raw:
                st.info("✅ Text extracted. Now using AI to clean up the list...")
                with st.spinner("🤖 Refining list with GPT..."):
                    try:
                        openai.api_key = OPENAI_KEY
                        ai_resp = openai.chat.completions.create(
                            model="gpt-4o-mini",  # Using a modern, efficient model
                            messages=[
                                {"role": "system",
                                 "content": "You turn raw OCR text from a shopping list into a precise list. Retain specific details like model or size. Return only a JSON array of strings."},
                                {"role": "user", "content": json.dumps(ocr_raw)}
                            ]
                        )
                        extracted = json.loads(ai_resp.choices[0].message.content)
                    except (json.JSONDecodeError, IndexError, Exception) as e:
                        st.warning(f"⚠️ AI cleanup failed: {e}. Using raw text instead.")
                        extracted = ocr_raw  # Fallback to raw OCR text if AI fails
            else:
                st.warning("⚠️ No text was detected in the uploaded image.")

    else:  # Chat with AI
        prompt = st.text_input("Describe your shopping needs (e.g., 'a new macbook pro and two t-shirts'):",
                               key="chat_prompt")
        if prompt and st.button("Generate List", key="search_ai"):
            with st.spinner("💡 Parsing with GPT..."):
                openai.api_key = OPENAI_KEY
                ai_resp = openai.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system",
                         "content": "You are a shopping assistant. Extract specific shopping items. Remove any unnecessary hyphens but Retain specific details like model or size. Return only a JSON array of strings."},
                        {"role": "user", "content": prompt}
                    ]
                )
                try:
                    extracted = json.loads(ai_resp.choices[0].message.content)
                except (json.JSONDecodeError, IndexError):
                    st.error("Could not parse items. Please rephrase your request.")
                    extracted = []

    if extracted:
        st.session_state.extracted_items = extracted

    # --- 5. CONFIRM & EDIT LIST ---
    if st.session_state.extracted_items:
        st.subheader("Confirm or Edit Your List")
        edited = st.data_editor(
            pd.DataFrame({"Items": st.session_state.extracted_items}),
            num_rows="dynamic", use_container_width=True
        )
        if st.button("Confirm List"):
            st.session_state.final_items = edited["Items"].dropna().tolist()
            st.session_state.filters_ready = False  # Reset to ensure filters are reapplied

    # --- 6. FILTERS & FETCH ---
    if st.session_state.final_items:
        st.subheader("Set Filters & Search")
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            st.session_state.site_pref = st.selectbox(
                "Retailer", ["Any", "Walmart", "Amazon", "Target", "Best Buy"], key="site_pref_selector"
            )
        with col2:
            st.session_state.sort_pref = st.selectbox(
                "Sort by", ["Balanced", "Cheapest", "Highest Rated"], key="sort_pref_selector"
            )
        with col3:
            st.markdown("<div style='padding-top: 28px;'></div>", unsafe_allow_html=True)
            if st.button("Find Best Picks", type="primary"):
                st.session_state.filters_ready = True
                st.session_state.why_explanations = {}

    # --- 7. DISPLAY RESULTS ---
    if st.session_state.get("filters_ready"):
        with st.spinner("🚀 Fetching and filtering products... This may take a moment."):
            with ThreadPoolExecutor() as executor:
                # The function will now only return (item_name, products)
                futures = [executor.submit(shopping.get_shopping_results, it, st.session_state.site_pref,
                                           st.session_state.sort_pref) for it in st.session_state.final_items]
                # Simplify the result unpacking
                all_results = {f.result()[0]: f.result()[1] for f in futures}

        # --- Display Product Picks ---
        st.subheader("Best Picks")
        cols = st.columns(2)
        item_index = 0
        for item, prods in all_results.items():
            with cols[item_index % 2]:
                with st.container(border=True):
                    st.markdown(f"<h4>{item}</h4>", unsafe_allow_html=True)
                    if not prods:
                        st.warning("No relevant products found for your criteria.")
                    else:
                        # (The rest of your product display logic remains the same)
                        top3 = prods[:3]
                        choice = st.selectbox(
                            "Select product:", top3,
                            format_func=lambda p: f"{p['title'][:50]}... - ${p.get('numeric_price', 0):.2f}",
                            key=f"choice_{item}", label_visibility="collapsed"
                        )
                        if choice:
                            if choice.get("thumbnail"): st.image(choice["thumbnail"], width=150)
                            st.markdown(f'<div class="product-price">${choice.get("numeric_price", 0):.2f}</div>',
                                        unsafe_allow_html=True)
                            st.write(f"**{choice['title']}**")

                            unique_id = choice.get('product_id') or choice.get('link')
                            explanation_key = f"explanation_{item}_{unique_id}"

                            if st.button("**Why?**", key=f"why_{item}"):
                                with st.spinner("🤖 Analyzing choice..."):
                                    explanation = shopping.get_why_explanation(item, choice, top3)
                                    st.session_state.why_explanations[explanation_key] = explanation

                            if explanation_key in st.session_state.why_explanations:
                                st.markdown(
                                    f"""<div class="why-explanation">💡 {st.session_state.why_explanations[explanation_key]}</div>""",
                                    unsafe_allow_html=True)

                            link = shopping.get_enhanced_direct_link(choice, st.session_state.site_pref)
                            if link: st.markdown(f'<a href="{link}" target="_blank" class="buy-button">Buy Now</a>',
                                                 unsafe_allow_html=True)
            item_index += 1

with right_col:
    st.markdown('<div class="scrollable-column">', unsafe_allow_html=True)

    # Always display the header for consistency
    st.subheader("Cart Total")

    # Display the cart content if results are ready, otherwise show a placeholder message
    if st.session_state.get("filters_ready"):
        ui.display_cart(st.session_state.final_items)
    else:
        st.info("Confirm your list and apply filters to see your cart.")

    st.markdown('</div>', unsafe_allow_html=True)