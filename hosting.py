# faber_customer_bot.py
import streamlit as st
from pymongo import MongoClient
from langchain_groq import ChatGroq
from langchain.prompts import PromptTemplate
from langchain.chains import LLMChain
import re
import random
from datetime import datetime
import json

# -----------------------------
# CONFIG - DOMAIN SPECIFIC
# -----------------------------
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "Dynamic"
CUSTOMERS_COL = "customers"
TICKETS_COL = "tickets"
CONV_COL = "conversations"

# Company-specific settings
COMPANY_NAME = "Faber"
COMPANY_DOMAIN = "Kitchen Chimneys & Exhaust Solutions"
COMPANY_PRODUCTS = "Kitchen Chimneys, Exhaust Hoods, Range Hoods"

# -----------------------------
# DB SETUP
# -----------------------------
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
customers = db[CUSTOMERS_COL]
tickets = db[TICKETS_COL]
conversations = db[CONV_COL]
orders = db["orders"]
technical_support = db["technical_support"]
billing = db["billing"]
products = db["products"]
returns = db["returns"]

# Create indexes for performance
customers.create_index("email", unique=False)
customers.create_index("name")
orders.create_index("order_id", unique=True)
orders.create_index("customer_email")
billing.create_index("order_id")
returns.create_index("order_id")
products.create_index("sku")
technical_support.create_index("issue")

# -----------------------------
# LLM SETUP
# -----------------------------
llm = ChatGroq(groq_api_key=st.secrets["groq_api_key"], model_name="gemma2-9b-it", temperature=0.3)

# -----------------------------
# SESSION STATE
# -----------------------------
if "messages" not in st.session_state:
    st.session_state["messages"] = []

if "conv_state" not in st.session_state:
    st.session_state["conv_state"] = {
        "phase": "entry",
        "logged_in": False,
        "customer_id": None,
        "customer_name": None,
        "attempts": 0,
        "context": {},
        "service_data": {}
    }

# -----------------------------
# UTILITIES
# -----------------------------
def get_installation_instructions():
    """Fallback installation instructions when LLM fails"""
    return """I'll help you with installation instructions for your Faber kitchen chimney:

**Safety Precautions:**
- Turn off main power supply
- Ensure proper ventilation
- Use safety equipment

**Tools Required:**
- Drill with masonry bits, screwdriver set, measuring tape, level

**Installation Steps:**
1. **Positioning**: Mount 24-30 inches above cooktop
2. **Wall Mounting**: Secure brackets to wall studs  
3. **Ducting**: Connect 6-inch duct to external vent
4. **Electrical**: Connect wiring (recommend professional)
5. **Filters**: Install baffle filters properly
6. **Testing**: Test all speeds and lighting

**Professional Installation**: Available for ₹2,500. Call 1800-XXX-FABER.

Do you need help with any specific step?"""



def generate_ticket_id():
    dt = datetime.utcnow().strftime("%Y%m%d")
    rand = random.randint(100000, 999999)
    return f"TKT-{dt}-{rand}"

def stamp():
    return datetime.utcnow().isoformat()

def log_conv_entry(role, text):
    rec = {
        "timestamp": stamp(),
        "role": role,
        "text": text,
        "session_info": st.session_state["conv_state"]
    }
    conversations.insert_one(rec)

def append_message(role, text):
    st.session_state.messages.append({"role": role, "content": text})
    log_conv_entry(role, text)

# -----------------------------
# LLM HELPER FUNCTIONS - DOMAIN AWARE
# -----------------------------
def smart_response(prompt_template, **kwargs):
    """Generate contextual response using LLM with domain context"""
    try:
        # Add company context to all prompts
        enhanced_template = f"""
        You are a professional customer service assistant for {COMPANY_NAME}, a leading {COMPANY_DOMAIN} company.
        Our main products include: {COMPANY_PRODUCTS}.
        
        {prompt_template}
        
        Always maintain a professional, helpful tone and use domain-appropriate terminology.
        Keep responses concise and action-oriented.
        """
        
        prompt = PromptTemplate(
            input_variables=list(kwargs.keys()),
            template=enhanced_template
        )
        chain = LLMChain(prompt=prompt, llm=llm)
        response = chain.run(**kwargs)
        return response.strip()
    except Exception as e:
        return f"I apologize, I'm having trouble processing that. Can you please rephrase?"

# -----------------------------
# DATA ACCESS FUNCTIONS - REAL DATA
# -----------------------------
def find_customer_by_email(email):
    """Find customer by email"""
    return customers.find_one({"email": {"$regex": email, "$options": "i"}}, {"_id": 0})

def find_customer_by_name(name):
    """Find customer by name"""
    return customers.find_one({"name": {"$regex": name, "$options": "i"}}, {"_id": 0})

def get_customer_orders(customer_email):
    """Get all orders for a customer - matches your schema"""
    return list(orders.find({"customer_email": {"$regex": customer_email, "$options": "i"}}, {"_id": 0}))

def get_order_by_id(order_id):
    """Get specific order by ID - matches your schema"""
    return orders.find_one({"order_id": order_id}, {"_id": 0})

def get_billing_info(order_id):
    """Get billing info by order ID - matches your schema"""
    return billing.find_one({"order_id": order_id}, {"_id": 0})

def get_return_info(order_id):
    """Get return info by order ID - matches your schema"""
    return returns.find_one({"order_id": order_id}, {"_id": 0})

def get_product_by_name_or_sku(query):
    """Find product by name or SKU - matches your schema"""
    return products.find_one({
        "$or": [
            {"name": {"$regex": query, "$options": "i"}},
            {"sku": {"$regex": query, "$options": "i"}}
        ]
    }, {"_id": 0})

def find_technical_solution(user_query):
    """Find technical support solution based on user query - matches your schema"""
    query_lower = user_query.lower()
    
    # Get all technical support documents
    tech_docs = list(technical_support.find({}, {"_id": 0}))
    
    # Find best match based on issue keywords
    for doc in tech_docs:
        issue = doc.get("issue", "").lower()
        if issue in query_lower or any(word in query_lower for word in issue.split()):
            return doc
    
    return None

# -----------------------------
# STREAMLIT UI
# -----------------------------
st.set_page_config(page_title=f"{COMPANY_NAME} Customer Service", layout="wide")

# Sidebar - Admin Controls
st.sidebar.title(f"{COMPANY_NAME} Admin")
st.sidebar.markdown(f"**{COMPANY_DOMAIN}**")

if st.sidebar.button("View Sample Data"):
    st.sidebar.write("**Customer:**", find_customer_by_email("alice@example.com"))
    st.sidebar.write("**Orders:**", len(get_customer_orders("alice@example.com")))
    st.sidebar.write("**Products:**", products.count_documents({}))
    st.sidebar.write("**Tech Issues:**", technical_support.count_documents({}))

if st.sidebar.button("Reset Chat"):
    st.session_state.messages = []
    st.session_state.conv_state = {
        "phase": "entry", "logged_in": False, "customer_id": None, 
        "customer_name": None, "attempts": 0, "context": {}, "service_data": {}
    }
    st.sidebar.success("Chat reset")

# Show database stats
st.sidebar.markdown("---")
st.sidebar.write("**Database Status:**")
st.sidebar.write(f"Customers: {customers.count_documents({})}")
st.sidebar.write(f"Orders: {orders.count_documents({})}")
st.sidebar.write(f"Products: {products.count_documents({})}")
st.sidebar.write(f"Support Issues: {technical_support.count_documents({})}")
st.sidebar.write(f"Tickets: {tickets.count_documents({})}")

# Main UI
st.title(f"{COMPANY_NAME} Customer Service")
st.caption(f"AI-powered support for {COMPANY_DOMAIN}")

# Initialize with domain-specific greeting
if st.session_state["conv_state"]["phase"] == "entry" and not st.session_state["messages"]:
    # Get time of day for more personalized greeting
    current_hour = datetime.now().hour
    time_greeting = "Good morning" if current_hour < 12 else "Good afternoon" if current_hour < 17 else "Good evening"
    
    try:
        greeting = smart_response("""
        Create a warm, professional greeting for Faber kitchen chimney customer service.
        
        Start with: "{time_greeting}! Welcome to Faber"
        
        Then include:
        - Brief introduction as their virtual assistant
        - Mention expertise in kitchen chimneys, installations, troubleshooting, orders, and service
        - Warm invitation to share how you can help
        - Keep it conversational and friendly (2-3 sentences max)
        
        Make it sound natural and welcoming, not robotic.
        """, time_greeting=time_greeting)
        
        if "apologize" in greeting or "trouble" in greeting:
            # Fallback to predefined greeting if LLM fails
            greeting = f"{time_greeting}! Welcome to Faber Customer Service. I'm your virtual assistant, here to help with all your kitchen chimney needs - from product questions and orders to technical support and installations. What can I help you with today?"
    except Exception:
        # Fallback greeting if LLM completely fails
        greeting = f"{time_greeting}! Welcome to Faber Customer Service. I'm your virtual assistant, here to help with all your kitchen chimney needs - from product questions and orders to technical support and installations. What can I help you with today?"
    
    append_message("assistant", greeting)
    st.session_state["conv_state"]["phase"] = "identify_customer"

# Display conversation
for msg in st.session_state.messages:
    if msg["role"] == "user":
        st.markdown(f"**You:** {msg['content']}")
    else:
        st.markdown(f"**{COMPANY_NAME} Bot:** {msg['content']}")

# Input handling
def user_submit():
    text = st.session_state.user_input.strip()
    if not text:
        return
    append_message("user", text)
    handle_user_input(text)
    st.session_state.user_input = ""

st.text_input("Type your message here:", key="user_input", on_change=user_submit)

# -----------------------------
# MAIN CONVERSATION HANDLER
# -----------------------------
def handle_user_input(text):
    state = st.session_state["conv_state"]
    phase = state["phase"]
    
    print(f"DEBUG: Phase={phase}, Input='{text}'")

    # Handle inappropriate language
    if any(word in text.lower() for word in ["idiot", "stupid", "shut up"]):
        response = smart_response("""
        The user used inappropriate language. Respond professionally, acknowledge their frustration,
        and guide them back to getting help with their kitchen chimney needs.
        """)
        append_message("assistant", response)
        return

    # ADD THIS NEW BLOCK IN ITS PLACE
    if phase == "identify_customer":
        lower_text = text.lower()

        # First, check for specific keywords to decide the path.
        if "guest" in lower_text:
            append_message("assistant", "Perfect! You're continuing as a guest. How can I help you with your kitchen chimney needs today?")
            append_message("assistant", show_main_menu())
            state["phase"] = "main_menu"
            return
    
        elif any(word in lower_text for word in ["existing", "have account", "previous", "ordered before", "@"]):
            append_message("assistant", "Great, I can help with that. Could you please provide the email address for your account?")
            state["phase"] = "verify_existing"
            return

        elif any(word in lower_text for word in ["new", "first time", "never ordered", "register"]):
            append_message("assistant", "Welcome to Faber! To get started, would you like to create an account or continue as a guest?")
            state["phase"] = "handle_new_customer" # This phase will handle their choice
            return

        # If NO keywords match (e.g., user just says "Hello"), then ask for clarification.
        # This is the ONLY response the bot will send for ambiguous inputs.
        else:
            fallback_message = "To better assist you, are you an existing Faber customer, new to our products, or would you prefer to continue as a guest?"
            clarify_response = smart_response("""
            User said: "{user_text}"
            This is their first message and it's not clear. Ask a friendly question to clarify if they are a new customer, existing customer, or want to be a guest.
            The question should be: "{fallback}"
            """, fallback_message=fallback_message, user_text=text, fallback=fallback_message)
        
            append_message("assistant", clarify_response)
            # Stay in the 'identify_customer' phase to wait for their answer.
            return

    # PHASE: IDENTIFY CUSTOMER
    if phase == "identify_customer":
        try:
            customer_type_response = smart_response("""
            User said: "{user_text}"
            
            Based on their message, determine if they are:
            1. An existing customer (mentions having an account, previous orders, or provides email)
            2. A new customer (says they're new, first time, or need to register)
            3. Need general information about kitchen chimneys
            
            Respond in a warm, conversational way:
            - If existing: "Great! Let me help you access your account. Could you share your email address?"
            - If new: "Welcome to Faber! Would you like to create an account for better service, or continue as a guest?"
            - If general: "I'd be happy to help with that! What would you like to know about our kitchen chimneys?"
            
            Keep it friendly, natural, and helpful. Don't list options - just respond conversationally.
            """, user_text=text)
            
            if "apologize" in customer_type_response or "trouble" in customer_type_response:
                # Fallback response
                customer_type_response = "I'd be happy to help you today! Are you an existing Faber customer, new to our products, or looking for general information about kitchen chimneys? Just let me know what brings you here."
        except Exception:
            customer_type_response = "I'd be happy to help you today! Are you an existing Faber customer, new to our products, or looking for general information about kitchen chimneys? Just let me know what brings you here."
        
        append_message("assistant", customer_type_response)
        
        # Route based on user intent
        lower_text = text.lower()

        if "guest" in lower_text:
            append_message("assistant", "Perfect! You're continuing as a guest. How can I help you with your kitchen chimney needs today?")
            append_message("assistant", show_main_menu())
            state["phase"] = "main_menu"
            return
        elif any(word in lower_text for word in ["existing", "have account", "previous", "ordered before", "@"]):
            state["phase"] = "verify_existing"
        elif any(word in lower_text for word in ["new", "first time", "never ordered", "register"]):
            state["phase"] = "handle_new_customer"
        else:
            clarify_response = smart_response("""
            User said: "{user_text}" but it's unclear if they are existing customer, new customer, or want to continue as guest.
            
            Ask them to clarify in a friendly way:
            "To better assist you, are you an existing Faber customer, new to our products, or would you prefer to continue as a guest?"
            """, user_text=text)
            
            if "apologize" in clarify_response:
                clarify_response = "To better assist you, are you an existing Faber customer, new to our products, or would you prefer to continue as a guest?"
            
            append_message("assistant", clarify_response)
            # Stay in identify_customer phase for clarification
            return

    # PHASE: VERIFY EXISTING CUSTOMER
    elif phase == "verify_existing":
        
        if "guest" in text.lower():
            append_message("assistant", "No problem! You're now continuing as a guest. How can I help you with your kitchen chimney needs today?")
            append_message("assistant", show_main_menu())
            state["phase"] = "main_menu"
            return
        
        email_match = re.search(r"[\w\.-]+@[\w\.-]+", text)
        
        if email_match:
            email = email_match.group(0)
            customer = find_customer_by_email(email)
            
            if customer:
                state["logged_in"] = True
                state["customer_id"] = customer["email"]
                state["customer_name"] = customer["name"]
                
                # Show their order history
                customer_orders = get_customer_orders(customer["email"])
                orders_info = ""
                if customer_orders:
                    orders_info = f"I can see you have {len(customer_orders)} order(s) with us. "
                
                welcome_response = smart_response("""
                Welcome back {customer_name}! {orders_info}
                
                How can I help you today? I can assist with:
                1. Order & Delivery Status
                2. Kitchen Chimney Technical Support
                3. Billing & Payments
                4. Product Information
                5. Returns & Exchange
                6. Account Management
                7. Service Complaints
                8. Connect with Human Agent
                
                What would you like help with?
                """, customer_name=customer["name"], orders_info=orders_info)
                
                append_message("assistant", welcome_response)
                state["phase"] = "main_menu"
                return
            else:
                state["attempts"] += 1
                if state["attempts"] >= 3:
                    append_message("assistant", "I couldn't find your account after multiple attempts. Would you like to register as a new customer or continue as a guest?")
                    state["phase"] = "handle_new_customer"
                else:
                    append_message("assistant", f"I couldn't find an account with {email}. Please double-check your email address (attempt {state['attempts']}/3) , or say 'guest' to continue without an account..")
        else:
            # Try name search
            customer = find_customer_by_name(text)
            if customer:
                confirm_response = smart_response("""
                Found customer: {customer_name} ({customer_email})
                Ask them to confirm if this is their account.
                """, customer_name=customer["name"], customer_email=customer["email"])
                append_message("assistant", confirm_response)
                state["context"]["pending_customer"] = customer
                state["phase"] = "confirm_customer"
            else:
                append_message("assistant", "Please provide your email address to find your account.")

    # PHASE: HANDLE NEW CUSTOMER
    elif phase == "handle_new_customer":
        # ADD: Handle guest request in new customer phase
        if "guest" in text.lower():
            append_message("assistant", "No problem! You can continue as a guest. How can I help you with your kitchen chimney needs today?")
            append_message("assistant", show_main_menu())
            state["phase"] = "main_menu"
            return
            
        if any(word in text.lower() for word in ["yes", "create", "register"]):
            append_message("assistant", "Great! Please provide: Full Name, Email, and Phone (optional). Format: John Doe | john@email.com | 9876543210")
            state["phase"] = "collect_registration"
        else:
            append_message("assistant", "No problem! You can continue as a guest. How can I help you with your kitchen chimney needs today?")
            append_message("assistant", show_main_menu())
            state["phase"] = "main_menu"

    # PHASE: CONFIRM CUSTOMER
    elif phase == "confirm_customer":
        if any(word in text.lower() for word in ["yes", "correct", "right", "that's me"]):
            customer = state["context"]["pending_customer"]
            state["logged_in"] = True
            state["customer_id"] = customer["email"]
            state["customer_name"] = customer["name"]
            
            append_message("assistant", f"Great! Welcome back {customer['name']}. How can I help you today?")
            append_message("assistant", show_main_menu()) 
            state["phase"] = "main_menu"
        else:
            append_message("assistant", "Let me try again. Please provide your email address.")
            state["phase"] = "verify_existing"

    # PHASE: COLLECT REGISTRATION
    elif phase == "collect_registration":
        email = re.search(r"[\w\.-]+@[\w\.-]+", text)
        phone = re.search(r"\b\d{10}\b", text)
        
        if email:
            email_val = email.group(0)
            name = re.sub(r'[\|,]', ' ', text.replace(email_val, "")).strip()
            if phone:
                name = name.replace(phone.group(0), "").strip()
            
            if not name or len(name) < 2:
                name = f"Customer{random.randint(1000,9999)}"
            
            phone_val = phone.group(0) if phone else ""
            
            # Create customer matching your schema
            customer = {
                "name": name,
                "email": email_val,
                "phone": phone_val,
                "status": "Active",
                "created_at": stamp()
            }
            customers.insert_one(customer)
            
            state["logged_in"] = True
            state["customer_id"] = email_val
            state["customer_name"] = name
            
            append_message("assistant", f"Welcome to Faber, {name}! Your account has been created. How can I help you today?")
            append_message("assistant", show_main_menu()) 
            state["phase"] = "main_menu"
        else:
            append_message("assistant", "Please provide a valid email address to create your account.")

    # PHASE: MAIN MENU - Service Selection
    elif phase == "main_menu":
        # Handle negative responses properly
        if any(word in text.lower().strip() for word in ["no", "nothing", "nope", "that's all", "goodbye", "bye"]):
            append_message("assistant", "Thank you for choosing Faber! Have a great day and enjoy your kitchen chimney. Feel free to reach out if you need any future support.")
            state["phase"] = "conversation_ended"
            return
            
        # Handle requests to go back
        if text.lower().strip() == "back":
            append_message("assistant", show_main_menu())
            return
        
        # Route to appropriate service handler with better keyword detection
        if any(word in text.lower() for word in ["order", "delivery", "track", "shipping", "1"]):
            handle_order_service(text)
        elif any(word in text.lower() for word in ["technical", "support", "noise", "not working", "installation", "install", "setup", "mount", "problem", "2"]):
            handle_technical_support(text)
        elif any(word in text.lower() for word in ["billing", "payment", "bill", "amount", "3"]):
            handle_billing_service(text)
        elif any(word in text.lower() for word in ["product", "chimney", "hood", "specs", "4"]):
            handle_product_info(text)
        elif any(word in text.lower() for word in ["return", "exchange", "defective", "5"]):
            handle_returns_service(text)
        elif any(word in text.lower() for word in ["account", "profile", "update", "6"]):
            handle_account_management(text)
        elif any(word in text.lower() for word in ["complaint", "service", "issue", "7"]):
            handle_complaints_service(text)
        elif any(word in text.lower() for word in ["human", "agent", "person", "8"]):
            handle_human_agent_request(text)
        else:
            # More intelligent clarification
            clarification = smart_response("""
            User said: "{user_text}" but it's not clear which service they need.
            
            Acknowledge their message naturally and guide them to the right service.
            Show the main menu options if needed.
            Be helpful and conversational.
            """, user_text=text)
            
            if "apologize" in clarification or "trouble" in clarification:
                clarification = f"I'd be happy to help with that! {show_main_menu()}"
                
            append_message("assistant", clarification)
    
    # ADD THIS NEW CONDITION
    elif phase == "collect_complaint":
        handle_collect_complaint(text)

    # PHASE: CONVERSATION ENDED
    elif phase == "conversation_ended":
        # Add debug output
        print(f"DEBUG: In conversation_ended phase, user input: '{text}'")
        print(f"DEBUG: text.lower(): '{text.lower()}'")
    
        # Expand the restart triggers
        restart_triggers = [
            "hello", "hi", "help", "question", "assistance", "assist", 
            "need", "want", "issue", "problem", "menu", "main menu", 
            "options", "service", "support", "start", "begin", "restart",
            "yes", "ok", "okay", "sure", "continue"
        ]
    
        # Check if any trigger matches
        if any(trigger in text.lower() for trigger in restart_triggers):
            print("DEBUG: Restarting conversation")
            append_message("assistant", "Welcome back! How can I help you with your Faber kitchen chimney today?")
            append_message("assistant", show_main_menu())
            state["phase"] = "main_menu"
        else:
            print("DEBUG: No trigger matched, staying in conversation_ended")
            append_message("assistant", "Thank you for contacting Faber! If you need any help in the future, just let me know.")
    
    #PHASE: Product Query 
    elif phase == "product_query":
        handle_product_query_phase(text)

    # PHASE: ORDER FOLLOWUP
    elif phase == "order_followup":
        handle_user_input_followup(text)
    
    # PHASE: TECH FOLLOWUP  
    elif phase == "tech_followup":
        handle_user_input_followup(text)

    # Handle any unmatched phases
    else:
        append_message("assistant", "Let me help you get back on track.")
        append_message("assistant", show_main_menu())
        state["phase"] = "main_menu"

# -----------------------------
# SERVICE HANDLERS - DOMAIN SPECIFIC
# -----------------------------
def handle_order_service(text):
    state = st.session_state["conv_state"]
    
    # Check for order ID
    order_match = re.search(r"ORD\d+", text.upper())
    
    if order_match:
        order_id = order_match.group(0)
        order = get_order_by_id(order_id)
        
        if order:
            response = smart_response("""
            Order found: {order_id}
            Product: {product}
            Status: {status}
            Delivery Date: {delivery_date}
            Customer: {customer_name}
            
            Present this information clearly and ask if they need help with anything else about this order.
            Don't immediately end the conversation - offer specific help related to their delivered chimney.
            """, 
            order_id=order["order_id"],
            product=order["product"],
            status=order["status"],
            delivery_date=order["delivery_date"],
            customer_name=order["customer_name"]
            )
        else:
            response = f"I couldn't find order {order_id}. Please check the order ID or provide your email."
        
        append_message("assistant", response)
        # Don't return to menu immediately - let them ask follow-up questions
        state["phase"] = "order_followup"
    
    elif state.get("customer_id"):
        # Show customer's orders
        customer_orders = get_customer_orders(state["customer_id"])
        
        if customer_orders:
            orders_text = "\n".join([
                f"• {order['order_id']} - {order['product']} - {order['status']}" 
                for order in customer_orders
            ])
            
            response = smart_response("""
            Here are your kitchen chimney orders:
            {orders_list}
            
            Which order would you like to know more about? Or what specific help do you need?
            """, orders_list=orders_text)
            
            append_message("assistant", response)
        else:
            append_message("assistant", "You don't have any orders yet. Would you like information about our kitchen chimney products?")
        
        state["phase"] = "order_followup"
    else:
        append_message("assistant", "Please provide your order ID (format: ORD123) to track your kitchen chimney order.")
        state["phase"] = "order_followup"

def handle_technical_support(text):
    # Find relevant technical solution from your database
    tech_solution = find_technical_solution(text)
    
    if tech_solution:
        steps_text = "\n".join([f"{i+1}. {step}" for i, step in enumerate(tech_solution["troubleshooting_steps"])])
        
        response = smart_response("""
        I found troubleshooting steps for "{issue}":
        
        {steps}
        
        Try these steps and let me know if this resolves your kitchen chimney issue.
        If the problem persists, I can create a service ticket for technical support.
        """, issue=tech_solution["issue"], steps=steps_text)
    else:
        # Check if user is asking for installation instructions
        if any(word in text.lower() for word in ["installation", "install", "setup", "mount"]):
            response = smart_response("""
            User is asking for installation instructions: "{user_query}"
            
            Provide helpful installation guidance for Faber kitchen chimneys:
            1. General installation steps
            2. Safety precautions
            3. Tools needed
            4. Offer detailed manual or professional installation service
            
            Be detailed and helpful about the installation process.
            """, user_query=text)
        else:
            response = smart_response("""
            User has a technical issue: "{user_query}"
            
            We don't have specific troubleshooting for this issue.
            Acknowledge their problem and offer to:
            1. Create a service ticket for technical support
            2. Connect them with our chimney specialist
            3. Schedule a service visit
            
            Be helpful and understanding about their kitchen chimney problem.
            """, user_query=text)
    
    append_message("assistant", response)
    state = st.session_state["conv_state"]
    state["service_data"]["tech_query"] = text
    state["phase"] = "tech_followup"

def handle_billing_service(text):
    order_match = re.search(r"ORD\d+", text.upper())
    
    if order_match:
        order_id = order_match.group(0)
        billing_info = get_billing_info(order_id)
        
        if billing_info:
            response = smart_response("""
            Billing information for order {order_id}:
            Bill ID: {bill_id}
            Customer: {customer_name}
            Amount: ₹{amount}
            Status: {status}
            
            Present this clearly and ask if they need help with payment or have billing questions.
            """,
            order_id=billing_info["order_id"],
            bill_id=billing_info["bill_id"],
            customer_name=billing_info["customer_name"],
            amount=billing_info["amount"],
            status=billing_info["status"]
            )
        else:
            response = f"No billing information found for {order_id}. Please verify the order ID."
    else:
        response = "Please provide your order ID (format: ORD123) to check billing information."
    
    append_message("assistant", response)
    return_to_menu()

def handle_product_info(text):
    # Check if this is just a menu selection (number only)
    if text.strip().isdigit():
        # User selected product info from menu - show available products or ask what they want
        response = smart_response("""
        User selected product information from the menu.
        
        Welcome them to product information and ask what specific product they'd like to know about.
        Mention that we have kitchen chimneys, range hoods, and exhaust solutions.
        Ask them to specify a product name or tell them to say "show all products" to see available options.
        """)
        
        append_message("assistant", response)
        
        # Set phase to collect product query
        state = st.session_state["conv_state"]
        state["phase"] = "product_query"
        return
    
    # Search for product in your database
    product = get_product_by_name_or_sku(text)
    
    if product:
        response = smart_response("""
        Product Information:
        Name: {name}
        SKU: {sku}
        Description: {description}
        Warranty: {warranty}
        
        Present this information clearly and ask if they need more details or want to place an order.
        """,
        name=product["name"],
        sku=product["sku"],
        description=product["description"],
        warranty=product["warranty"]
        )
    else:
        # Check if user wants to see all products
        if "show all" in text.lower() or "all products" in text.lower():
            # Get all products from database
            all_products = list(products.find({}, {"_id": 0}))
            if all_products:
                products_text = "\n".join([
                    f"• {product['name']} ({product['sku']}) - {product['description'][:50]}..." 
                    for product in all_products
                ])
                response = smart_response("""
                Here are our available kitchen chimney products:
                {products_list}
                
                Which product would you like detailed information about?
                """, products_list=products_text)
            else:
                response = "I don't see any products in our current catalog. Let me connect you with our product specialist."
        else:
            response = smart_response("""
            User asked about: "{product_query}"
            
            We don't have specific information for this product.
            Mention that we specialize in kitchen chimneys and exhaust hoods.
            Ask them to be more specific about which product they want to know about.
            Offer to show all available products or connect them with product specialist.
            """, product_query=text)
    
    append_message("assistant", response)
    return_to_menu()


def handle_returns_service(text):
    state = st.session_state["conv_state"]
    order_match = re.search(r"ORD\d+", text.upper())
    
    if order_match:
        order_id = order_match.group(0)
        return_info = get_return_info(order_id)
        
        if return_info:
            response = smart_response("""
            Return information for order {order_id}:
            Return ID: {return_id}
            Product: {product}
            Reason: {reason}
            Status: {status}
            
            Present this information and ask if they need help with the return process.
            """,
            order_id=return_info["order_id"],
            return_id=return_info["return_id"],
            product=return_info["product"],
            reason=return_info["reason"],
            status=return_info["status"]
            )
        else:
            response = f"No return request found for {order_id}. Would you like to initiate a return?"
    else:
        response = "Please provide your order ID (ORD123) to check return status or initiate a return."
    
    append_message("assistant", response)
    return_to_menu()

def handle_account_management(text):
    state = st.session_state["conv_state"]
    
    if not state["logged_in"]:
        append_message("assistant", "Please log in to manage your account. Would you like me to help you access your account?")
    else:
        response = smart_response("""
        Customer {customer_name} wants account help.
        
        Offer to help them:
        1. Update contact information
        2. View order history
        3. Change preferences
        4. Update delivery address
        
        Ask what specifically they'd like to update.
        """, customer_name=state.get("customer_name", ""))
        append_message("assistant", response)
    
    return_to_menu()

def handle_complaints_service(text):
    """
    Step 1 (The "Ask"): This function no longer creates a ticket.
    Its only job is to ask for information and set the stage for the next step.
    """
    state = st.session_state["conv_state"]

    if state.get("logged_in"):
        # If the user is known, just ask for the problem description.
        append_message("assistant", "I'm sorry to hear you're having an issue. Please describe your complaint in detail, and I will create a ticket for you.")
    else:
        # If the user is a guest, ask for contact info and the problem.
        append_message("assistant", "I can certainly help with that. To file a service complaint as a guest, I'll need a few details.")
        append_message("assistant", "Please provide your **Full Name**, **Email Address**, and a **detailed description** of the problem.")
    
    # This is the most important change:
    # Tell the bot to move to the 'collect_complaint' phase and wait for the user's reply.
    state["phase"] = "collect_complaint"

def handle_collect_complaint(text):
    """
    Step 2 (The "Listen and Create"): This function runs AFTER the user replies.
    It takes their detailed response and creates an actionable ticket.
    """
    state = st.session_state["conv_state"]
    customer_email = state.get("customer_email", "guest")
    
    # If the user was a guest, parse their details from the message
    if customer_email == "guest":
        email_match = re.search(r"[\w\.-]+@[\w\.-]+", text)
        if not email_match:
            append_message("assistant", "A valid email is required to create a ticket. Please provide your details again, including your email.")
            return # Stay in this phase to give them another chance
        
        guest_email = email_match.group(0)
        complaint_details = text
        ticket_customer_id = guest_email # Use the provided guest email for the ticket
        
    else: # The user was already logged in
        complaint_details = text
        ticket_customer_id = customer_email # Use the logged-in user's email

    # Create the service ticket with the detailed information
    ticket_id = generate_ticket_id()
    ticket = {
        "ticket_id": ticket_id,
        "customer_email": ticket_customer_id,
        "complaint": complaint_details,
        "status": "open",
        "priority": "P2",
        "created_at": stamp()
    }
    tickets.insert_one(ticket)
    
    append_message("assistant", f"Thank you. Your service ticket is **{ticket_id}**. Our team will contact you at **{ticket_customer_id}** within 24 hours.")
    return_to_menu()

def handle_human_agent_request(text):
    response = smart_response("""
    User wants to speak with human agent.
    
    Acknowledge their request professionally.
    Ask for phone number verification.
    Explain handoff process and estimated wait time.
    Provide reference number: HANDOFF-{ref_num}
    """, ref_num=random.randint(1000, 9999))
    
    append_message("assistant", response)
    return_to_menu()

def handle_product_query_phase(text):
    """Handle the product query collection phase"""
    state = st.session_state["conv_state"]
    
    if any(word in text.lower() for word in ["back", "menu", "cancel"]):
        append_message("assistant", show_main_menu())
        state["phase"] = "main_menu"
        return
    
    # Process the actual product query
    handle_product_info(text)
    state["phase"] = "main_menu"  # Return to main menu after handling

def show_main_menu():
    """Return main menu text"""
    return """How can I help you today? I can assist with:

1. Order & Delivery Status
2. Kitchen Chimney Technical Support  
3. Billing & Payments
4. Product Information
5. Returns & Exchange
6. Account Management
7. Service Complaints
8. Connect with Human Agent

What would you like help with?"""

def return_to_menu():
    """Return to main menu"""
    state = st.session_state["conv_state"]
    state["phase"] = "main_menu"
    
    response = smart_response("""
    Ask if there's anything else you can help them with in a natural way.
    Don't be repetitive - vary the language.
    """)
    if "apologize" in response or "trouble" in response:
        response = "Is there anything else I can help you with regarding your Faber kitchen chimney?"
    
    append_message("assistant", response)

# Handle phase-specific follow-ups
def handle_user_input_followup(text):
    """Handle follow-up phases with better installation support"""
    state = st.session_state["conv_state"]
    
    if state["phase"] == "order_followup":
        # MAIN FIX: Handle installation requests with fallback
        if any(word in text.lower() for word in ["installation", "install", "setup", "mount", "instructions"]):
            try:
                # Try LLM first
                response = smart_response("""
                User is asking for installation instructions for their Faber kitchen chimney.
                
                Provide comprehensive installation guidance:
                1. Safety precautions and tools needed
                2. Step-by-step mounting process
                3. Electrical connections
                4. Duct installation
                5. Testing the chimney
                6. Offer professional installation service
                
                Be detailed and helpful about the installation process.
                """)
                
                # Check if LLM response is the error message
                if "apologize" in response and "trouble" in response:
                    # Use fallback instructions
                    response = get_installation_instructions()
                    
            except Exception:
                # Use fallback if LLM completely fails
                response = get_installation_instructions()
            
            append_message("assistant", response)
            return
        
        # Handle gratitude/thanks without creating tickets
        if any(word in text.lower() for word in ["thank", "thanks", "appreciate"]):
            response = "You're welcome! I'm glad I could help with your installation instructions. Is there anything else about your Faber chimney I can assist you with?"
            append_message("assistant", response)
            return
        
        # Handle negative responses (no, nothing, etc.)
        if any(word in text.lower().strip() for word in ["no", "nothing", "nope", "that's all", "goodbye", "bye"]):
            response = "Thank you for choosing Faber! Have a great day and enjoy your new kitchen chimney. Feel free to reach out if you need any future support."
            append_message("assistant", response)
            state["phase"] = "conversation_ended"
            return
        
        # Check for order ID in follow-up
        order_match = re.search(r"ORD\d+", text.upper())
        if order_match:
            handle_order_service(text)
        else:
            # General follow-up response
            response = smart_response("""
            User said: "{user_text}" in context of order discussion.
            
            Provide helpful response related to their order or kitchen chimney.
            If unclear, ask clarifying questions politely.
            """, user_text=text)
            append_message("assistant", response)
    
    elif state["phase"] == "tech_followup":
        # Handle gratitude without creating tickets
        if any(word in text.lower() for word in ["thank", "thanks", "appreciate"]):
            response = "You're welcome! I'm glad I could help. If you have any other questions about your Faber kitchen chimney, feel free to ask."
            append_message("assistant", response)
            return
            
        # Handle requests to go back or negative responses
        if any(word in text.lower() for word in ["back", "no", "nothing", "cancel"]):
            response = "No problem! How else can I help you today?"
            append_message("assistant", show_main_menu())
            state["phase"] = "main_menu"
            return
        
        if any(word in text.lower() for word in ["yes", "worked", "fixed", "resolved"]):
            append_message("assistant", "Great! I'm glad the troubleshooting steps helped resolve your kitchen chimney issue.")
            return_to_menu()
        else:
            # Only create ticket if they actually need further help
            if any(word in text.lower() for word in ["still", "not working", "problem", "issue", "help"]):
                ticket_id = generate_ticket_id()
                ticket = {
                    "ticket_id": ticket_id,
                    "customer_email": state.get("customer_id", "guest"),
                    "issue": state["service_data"].get("tech_query", ""),
                    "status": "open",
                    "priority": "P2",
                    "created_at": stamp()
                }
                tickets.insert_one(ticket)
                
                append_message("assistant", f"I've created a service ticket ({ticket_id}) for technical support. Our chimney specialist will contact you within 24 hours.")
                return_to_menu()
            else:
                # General tech response
                response = smart_response("""
                User said: "{user_text}" in technical support context.
                Provide appropriate response without creating unnecessary tickets.
                """, user_text=text)
                append_message("assistant", response)

# -----------------------------
# TESTING SECTION
# -----------------------------
st.markdown("---")
st.markdown("**🧪 Faber Chimney Bot - Testing Guide**")

with st.expander("Domain-Specific Test Cases"):
    st.markdown("""
    **Real Data Integration:**
    - Customer: "alice@example.com" (Alice Example)
    - Order: "ORD123" (Faber Hood Alpha - Delivered)
    - Billing: "BILL123" (₹12,000 - Paid)
    - Return: "RET123" (Defective motor - In Progress)
    
    **Technical Support (Real Issues):**
    - "There's noise in my chimney" → Filter cleaning steps
    - "Installation help needed" → Mounting & setup steps  
    - "Chimney not working" → Power & maintenance steps
    
    **Product Information:**
    - "Tell me about Faber Hood Alpha"
    - "FAB-001 specifications"
    
    **Complete Workflows:**
    1. Login → Track order → Check billing
    2. Guest → Technical issue → Create ticket
    3. Return customer → Product inquiry → Human agent
    """)

with st.expander("Plug & Play Features"):
    st.markdown("""
    **Domain Adaptability:**
    - Change `COMPANY_NAME`, `COMPANY_DOMAIN`, `COMPANY_PRODUCTS`
    - Update `DB_NAME` and collection names
    - Modify data schema mappings in functions
    - LLM automatically adapts language and terminology
    
    **Data-Driven:**
    - All responses use real MongoDB data
    - No hardcoded sample data
    - Dynamic troubleshooting from database
    - Real customer/order/product lookups
    """)

st.markdown(f"**Current Customer:** {st.session_state['conv_state'].get('customer_name', 'Guest')}")
st.markdown(f"**Phase:** {st.session_state['conv_state']['phase']}")