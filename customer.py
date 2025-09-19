import streamlit as st
from pymongo import MongoClient
from langchain_groq import ChatGroq
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
import json

# -----------------------------
# MongoDB Details
# -----------------------------
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "Dynamic"
COLLECTION_NAME = "sample"

# Replace with your Groq key
GROQ_API_KEY = "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"

# -----------------------------
# LLM Setup
# -----------------------------
llm = ChatGroq(groq_api_key=GROQ_API_KEY, model_name="gemma2-9b-it")

# -----------------------------
# Streamlit Config
# -----------------------------
st.set_page_config(page_title="Customer Service Chatbot", page_icon="💬", layout="wide")

st.markdown("""
    <style>
        .stTextInput>label {
            font-size: 24px;
            font-weight: bold;
        }
        .custom-header {
            font-size: 30px;
            font-weight: bold;
            color: #333333;
        }
    </style>
""", unsafe_allow_html=True)

st.markdown('<p class="custom-header">Welcome to Customer Service! How can I assist you today?</p>', unsafe_allow_html=True)

# -----------------------------
# Session State
# -----------------------------
if 'messages' not in st.session_state:
    st.session_state.messages = []

if 'input' not in st.session_state:
    st.session_state.input = ""

# -----------------------------
# MongoDB Connection
# -----------------------------
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

# -----------------------------
# Load FAQ Knowledge Base (JSON)
# -----------------------------
def load_faq_json(path="faq.json"):
    with open(path, "r", encoding="utf-8") as f:
        faq_data = json.load(f)
    return "\n".join([f"Q: {item['question']} | A: {item['answer']}" for item in faq_data])

faq_text = load_faq_json("faq.json")

# -----------------------------
# DB Helpers
# -----------------------------
def get_customer_info(name):
    """Fetch customer info from DB."""
    result = collection.find_one({"name": {"$regex": name, "$options": "i"}})
    if result:
        return f"Customer: {result.get('name')} | Email: {result.get('email')} | Status: {result.get('status','Active')}"
    else:
        return None

def register_customer(name, email):
    """Register a new customer."""
    collection.insert_one({"name": name, "email": email, "status": "Active"})
    return f"✅ Registered new customer: {name} ({email})"

# -----------------------------
# Response Generator
# -----------------------------
def generate_response(user_input):
    prompt = PromptTemplate(
        input_variables=["faq_text", "user_input"],
        template="""
You are a professional customer service chatbot. 
Only answer questions related to customer service. 
If unrelated, say: "Sorry, I can only assist with customer service-related queries."
Be polite and user friendly so that the customer is interested and looking forward to have a plesent conversation with you.

Here is the knowledge base you can use, make sure you check according to the query if you can find any query similar and reply accordingly and yu can even make the answer sound better if you want to at times it's on you but make sure the answers are customer satisfactory:
{faq_text}

Customer Query: {user_input}
        """
    )

    llm_chain = LLMChain(prompt=prompt, llm=llm)
    response = llm_chain.run(faq_text=faq_text, user_input=user_input)
    return response

# -----------------------------
# Chat Display
# -----------------------------
for message in st.session_state.messages:
    col1, col2 = st.columns([1, 4])

    with col1:
        st.empty()

    with col2:
        user_style = """
            background-color: #E8E8E8;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 10px;
            box-shadow: 0px 2px 5px rgba(0,0,0,0.1);
        """
        bot_style = """
            background-color: #DCF8C6;
            padding: 10px;
            border-radius: 5px;
            margin-bottom: 10px;
            box-shadow: 0px 2px 5px rgba(0,0,0,0.1);
        """

        if message["role"] == "user":
            st.markdown(f"<div style='{user_style}'>{message['content']}</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"<div style='{bot_style}'>{message['content']}</div>", unsafe_allow_html=True)

# -----------------------------
# Input Handler
# -----------------------------
def process_input():
    user_input = st.session_state.input
    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        response = generate_response(user_input)
        st.session_state.messages.append({"role": "assistant", "content": response})
        st.session_state.input = ""

user_input = st.text_input(
    "",
    value=st.session_state.input,
    key="input",
    on_change=process_input
)

st.sidebar.title("💬 Customer Service Bot")
st.sidebar.info("Handles complaints, tickets, refunds, troubleshooting and more. Powered by Groq LLM")
