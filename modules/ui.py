# modules/ui.py

import streamlit as st
from PIL import Image
import pandas as pd
from pathlib import Path # Import the Path object

def load_css(file_path):
    """Loads a CSS file into the Streamlit app."""
    with open(file_path) as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

def setup_page():
    """Sets up the Streamlit page configuration and loads CSS."""
    st.set_page_config(
        page_title="ShopAI - Smart Shopping",
        page_icon="🛒",
        layout="wide"
    )
    load_css("assets/styles.css")

def display_sidebar():
    """Displays the sidebar with logo and app description."""
    with st.sidebar:
        project_root = Path(__file__).parent.parent
        logo_path = project_root / "assets" / "Logo.png"

        try:
            logo = Image.open(logo_path)
            st.image(logo)
        except FileNotFoundError:
            st.error("Logo not found!")  # Show a more specific error
            st.header("ShopAI")
        st.markdown("---")
        st.markdown(
            '<span class="app-summary-text">"AI-Powered Shopping. Human-Level Savings."</span>',
            unsafe_allow_html=True
        )
        st.markdown("\n")
        st.markdown(
            "ShopAI is your intelligent shopping assistant. Easily upload your handwritten lists or chat with AI to find the best prices and products across various retailers, making your shopping experience smarter and more efficient."
        )


def display_cart(final_items):
    """Displays the shopping cart and total value with custom styling."""
    cart_items = []
    total_price = 0.0

    for idx, item in enumerate(final_items):
        choice_key = f"choice_{item}"
        if choice_key in st.session_state:
            selected_product = st.session_state[choice_key]
            if selected_product:
                price_value = selected_product.get('numeric_price', 0.0)
                cart_items.append({
                    "S.No.": idx + 1,
                    "Product": selected_product['title'],
                    "Price": price_value
                })
                total_price += price_value

    if cart_items:
        cart_df = pd.DataFrame(cart_items)

        def style_table(df):
            """Applies custom CSS styling to the cart DataFrame."""
            styled_df = df.style.hide(axis="index")

            header_styles = [
                {'selector': 'th',
                 'props': [('background-color', '#F66433'), ('color', 'white'), ('font-weight', 'bold'),
                           ('border', '1px #F66433')]}
            ]
            body_styles = [
                {'selector': 'td',
                 'props': [('background-color', 'transparent'), ('color', 'black'), ('border', '1px #F66433')]}
            ]
            table_border_style = [
                {'selector': '', 'props': [('border-collapse', 'collapse'), ('border', '1px #F66433')]}
            ]

            styled_df = styled_df.format({"S.No.": "{:d}".format, "Price": "${:.2f}"}) \
                .set_table_styles(header_styles + body_styles + table_border_style) \
                .set_properties(**{'width': 'auto', 'text-align': 'left'})

            styled_df = styled_df.set_properties(subset=['S.No.'], **{'width': '50px', 'text-align': 'center'}) \
                .set_properties(subset=['Product'], **{'width': '270px'}) \
                .set_properties(subset=['Price'], **{'width': '200'})

            return styled_df

        # Use st.markdown with the styled HTML, not st.dataframe
        st.markdown(
            style_table(cart_df).to_html(escape=False),
            unsafe_allow_html=True
        )

        st.markdown("---")
        st.metric(label="**Total Cart Value**", value=f"${total_price:,.2f}")
    else:
        st.info("Your cart is empty. Apply filters and select products to add them here.")