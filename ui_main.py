import RPi.GPIO as GPIO
import board
import busio
import adafruit_ssd1306
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime
import time
import sqlite3
import random
import os
import pickle

TODAY_CONTACTS_FILE = 'today_contacts.pkl'

# Function to save today's contacts to a file so they persist
def save_today_contacts(contacts):
    with open(TODAY_CONTACTS_FILE, 'wb') as f:
        pickle.dump(contacts, f)

# Function to load today's contacts from the file, if they exist
def load_today_contacts():
    if os.path.exists(TODAY_CONTACTS_FILE):
        with open(TODAY_CONTACTS_FILE, 'rb') as f:
            return pickle.load(f)
    return None

# Function to check if the day has changed (for resetting the contacts)
def is_new_day():
    today_date = datetime.today().strftime('%Y-%m-%d')
    if os.path.exists(TODAY_CONTACTS_FILE):
        last_modified_date = datetime.fromtimestamp(os.path.getmtime(TODAY_CONTACTS_FILE)).strftime('%Y-%m-%d')
        return today_date != last_modified_date
    return True

# Function to manage today's contacts and check if they need to be reset
def get_today_contacts():
    if is_new_day() or not load_today_contacts():
        eligible_contacts = get_contactable_contacts()
        if eligible_contacts:
            today_contacts = suggest_contacts_for_today(eligible_contacts)
            save_today_contacts(today_contacts)
        else:
            today_contacts = []
    else:
        today_contacts = load_today_contacts()

    return today_contacts


# Function to log a contact event
def log_event(contact_id, event_type):
    """Log a contact event in the contacts_events.db database."""
    conn = sqlite3.connect('contacts_events.db')  # Using the correct database
    cursor = conn.cursor()

    today = datetime.today().strftime('%Y-%m-%d')

    # Get user input for rating the interaction
    rating = int(input("Rate the quality of the contact (1-5): "))

    # Insert the event into the events table
    cursor.execute('''
        INSERT INTO events (contact_id, event_type, event_date, rating)
        VALUES (?, ?, ?, ?)
    ''', (contact_id, event_type, today, rating))

    # Update the contact's last_contact_date in contacts.db
    conn_contact = sqlite3.connect('contacts.db')  # Access the contacts database
    cursor_contact = conn_contact.cursor()
    cursor_contact.execute('''
        UPDATE contacts
        SET last_contact_date = ?
        WHERE id = ?
    ''', (today, contact_id))

    conn_contact.commit()
    conn_contact.close()

    conn.commit()
    conn.close()
    print(f"Logged {event_type} for contact with ID {contact_id}, rated {rating}/5.")

# Function to handle event logging after contact interaction
def handle_contact_interaction(contact_id, contact_name):
    """Prompt the user to log the contact event."""
    print(f"Logging event for {contact_name}")
    
    # Ask what type of contact occurred
    event_type = input("What kind of contact was this? (email, phone call, in-person): ")

    # Log the event and update the database
    log_event(contact_id, event_type)
    
def get_all_contacts():
    """Retrieve all contacts from the contacts_events.db."""
    conn = sqlite3.connect('contacts_events.db')
    cursor = conn.cursor()

    # Fetch all contacts
    cursor.execute("SELECT id, name FROM contacts")
    contacts = cursor.fetchall()

    conn.close()
    return contacts

# Function to retrieve contacts eligible for contacting
def get_contactable_contacts():
    conn = sqlite3.connect('contacts.db')
    cursor = conn.cursor()

    today = datetime.today().date()

    cursor.execute("""
        SELECT id, name, frequency, last_contact_date 
        FROM contacts
        WHERE julianday(?) - julianday(last_contact_date) >= frequency
    """, (today,))
    
    contacts = cursor.fetchall()
    conn.close()

    print(f"Eligible contacts: {contacts}")  # Add this print statement

    return contacts

# Function to randomly select 3 contacts from the eligible list
def suggest_contacts_for_today(eligible_contacts):
    """Select 3 random contacts from the eligible pool."""
    if len(eligible_contacts) < 3:
        return eligible_contacts  # If fewer than 3 contacts are eligible, return all of them
    else:
        return random.sample(eligible_contacts, 3)

# Function to display the "Today" menu with contacts or a "No contacts today!" message
def display_today_menu(contacts, current_selection):
    """Display the list of contacts for today, or show a 'No contacts today!' message."""
    oled.fill(0)
    image = Image.new("1", (oled.width, oled.height))
    draw = ImageDraw.Draw(image)

    if contacts:
        # Display the current contact and surrounding contacts
        options = [
            contacts[current_selection - 1] if current_selection > 0 else contacts[-1],  # Previous contact
            contacts[current_selection],  # Current selected contact
            contacts[current_selection + 1] if current_selection < len(contacts) - 1 else contacts[0]  # Next contact
        ]

        draw.text((0, 0), options[0][0], font=font, fill=255)  # Previous contact
        draw.text((0, 14), "> " + options[1][0], font=font, fill=255)  # Current selected contact
        draw.text((0, 28), options[2][0], font=font, fill=255)  # Next contact
    else:
        # If no contacts, display the "No contacts today!" message
        draw.text((oled.width // 2 - 50, oled.height // 2 - 10), "No contacts today!", font=font, fill=255)

    # Draw labels for Back and OK buttons at the bottom
    draw.text((oled.width - 25, oled.height - 10), "OK", font=font, fill=255)
    draw.text((0, oled.height - 10), "Back", font=font, fill=255)

    # Update the OLED display
    oled.image(image)
    oled.show()

# Function to handle the "Today" menu navigation
def today_menu(contacts):
    """Allow the user to navigate through the 'Today' contacts or see the 'No contacts' message."""
    current_selection = 0
    display_today_menu(contacts, current_selection)

    while True:
        if GPIO.input(UP_BUTTON_PIN) == GPIO.LOW:  # Scroll up
            if contacts:
                current_selection = (current_selection - 1) % len(contacts)
                display_today_menu(contacts, current_selection)
            time.sleep(0.3)  # Debounce

        if GPIO.input(DOWN_BUTTON_PIN) == GPIO.LOW:  # Scroll down
            if contacts:
                current_selection = (current_selection + 1) % len(contacts)
                display_today_menu(contacts, current_selection)
            time.sleep(0.3)  # Debounce

        if GPIO.input(CONFIRM_BUTTON_PIN) == GPIO.LOW:  # OK button pressed
            if contacts:
                contact = contacts[current_selection]
                contact_id, contact_name = contact[0], contact[0]  # Adjust this if ID is a different field
                handle_contact_interaction(contact_id, contact_name)  # Log event for selected contact
            time.sleep(0.3)  # Debounce

        if GPIO.input(BACK_BUTTON_PIN) == GPIO.LOW:  # Back button pressed
            print("Back to main menu")
            return  # Return to the previous screen (Main Menu)

# Main function to manage daily contact suggestions
def daily_contact_suggestions():
    """Pull eligible contacts, suggest 3 for today, and display them."""
    eligible_contacts = get_contactable_contacts()  # Step 1: Get eligible contacts
    if eligible_contacts:
        suggested_contacts = suggest_contacts_for_today(eligible_contacts)  # Step 2: Randomly select 3 contacts
        today_menu(suggested_contacts)  # Step 3: Display the contacts in a menu format
    else:
        today_menu([])  # If no eligible contacts, show "No contacts today!"
        
def display_contacts_menu(contacts, current_selection):
    """Display all contacts in a scrollable menu."""
    oled.fill(0)
    image = Image.new("1", (oled.width, oled.height))
    draw = ImageDraw.Draw(image)

    # Display the current contact and surrounding contacts
    options = [
        contacts[current_selection - 1] if current_selection > 0 else contacts[-1],  # Previous contact
        contacts[current_selection],  # Current selected contact
        contacts[current_selection + 1] if current_selection < len(contacts) - 1 else contacts[0]  # Next contact
    ]

    draw.text((0, 0), options[0][1], font=font, fill=255)  # Previous contact
    draw.text((0, 14), "> " + options[1][1], font=font, fill=255)  # Current selected contact
    draw.text((0, 28), options[2][1], font=font, fill=255)  # Next contact

    # Draw labels for Back and OK buttons at the bottom
    draw.text((oled.width - 25, oled.height - 10), "OK", font=font, fill=255)
    draw.text((0, oled.height - 10), "Back", font=font, fill=255)

    # Update the OLED display
    oled.image(image)
    oled.show()

# Function to navigate through the contacts
def contacts_menu():
    """Allow the user to scroll through the list of contacts."""
    contacts = get_all_contacts()
    current_selection = 0
    display_contacts_menu(contacts, current_selection)

    while True:
        if GPIO.input(UP_BUTTON_PIN) == GPIO.LOW:  # Scroll up
            current_selection = (current_selection - 1) % len(contacts)
            display_contacts_menu(contacts, current_selection)
            time.sleep(0.3)  # Debounce

        if GPIO.input(DOWN_BUTTON_PIN) == GPIO.LOW:  # Scroll down
            current_selection = (current_selection + 1) % len(contacts)
            display_contacts_menu(contacts, current_selection)
            time.sleep(0.3)  # Debounce

        if GPIO.input(CONFIRM_BUTTON_PIN) == GPIO.LOW:  # OK button pressed
            print(f"Selected contact: {contacts[current_selection][1]}")  # Action on contact selection
            time.sleep(0.3)  # Debounce

        if GPIO.input(BACK_BUTTON_PIN) == GPIO.LOW:  # Back button pressed
            print("Back to main menu")
            return  # Return to the previous screen
# Your OLED, GPIO, and other imports here

# Add the helper functions here


# Function to retrieve contacts eligible for contacting based on their last contact date and frequency
def get_contactable_contacts():
    """Retrieve contacts that are eligible for contacting based on their last contact date and frequency."""
    conn = sqlite3.connect('contacts_events.db')
    cursor = conn.cursor()

    today = datetime.today().strftime('%Y-%m-%d')

    # Query to find contacts where the difference between today and last_contact_date exceeds frequency
    cursor.execute('''
        SELECT id, name, frequency, last_contact_date 
        FROM contacts
        WHERE julianday(?) - julianday(last_contact_date) >= frequency
    ''', (today,))
    
    contacts = cursor.fetchall()
    conn.close()

    return contacts

# Function to randomly select 3 contacts from the eligible list
def suggest_contacts_for_today(eligible_contacts):
    """Select 3 random contacts from the eligible pool."""
    if len(eligible_contacts) <= 3:
        return eligible_contacts  # If fewer than 3 contacts are eligible, return all of them
    else:
        import random
        return random.sample(eligible_contacts, 3)

# Main function to handle the "Today" suggestions
def daily_contact_suggestions():
    """Pull eligible contacts, suggest 3 for today, and display them."""
    eligible_contacts = get_contactable_contacts()
    if eligible_contacts:
        suggested_contacts = suggest_contacts_for_today(eligible_contacts)
        # Display logic (as per your existing UI code) for these contacts
        print(f"Suggested contacts for today: {suggested_contacts}")
    else:
        print("No contacts are eligible for today.")
        
        

def log_event_to_db(contact_id, event_type, rating):
    """Log the event in the contacts_events.db database and update the contact's last_contact_date."""
    conn = sqlite3.connect('contacts_events.db')
    cursor = conn.cursor()

    today = datetime.today().strftime('%Y-%m-%d')

    # Insert the event into the events table
    cursor.execute('''
        INSERT INTO events (contact_id, event_type, event_date, rating)
        VALUES (?, ?, ?, ?)
    ''', (contact_id, event_type, today, rating))

    # Update the contact's last_contact_date in the contacts table
    cursor.execute('''
        UPDATE contacts
        SET last_contact_date = ?
        WHERE id = ?
    ''', (today, contact_id))

    conn.commit()
    conn.close()
    print("Event logged successfully!")


# GPIO setup
UP_BUTTON_PIN = 17
DOWN_BUTTON_PIN = 27
BACK_BUTTON_PIN = 22
CONFIRM_BUTTON_PIN = 23

GPIO.setmode(GPIO.BCM)
GPIO.setup(UP_BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(DOWN_BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(BACK_BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(CONFIRM_BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# OLED display setup
i2c = busio.I2C(board.SCL, board.SDA)
oled = adafruit_ssd1306.SSD1306_I2C(128, 64, i2c)

####################UI SECTION##################################


############# MAIN MENU ####################

# Menu options
menu_options = ["Today", "Log Event", "Contacts"]
current_selection = 0

# Load fonts
font = ImageFont.load_default()
large_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)  # Larger font for the selected menu item

# Draw the scroll bar

def draw_scroll_bar(draw, selected, total_items):
    """Draw a dotted scroll bar with a filled section for the selected item."""
    bar_width = 3
    total_height = oled.height - 10  # 10 pixels reserved for the OK button area at the bottom
    top_padding = 5
    bottom_padding = 5
    available_height = total_height - top_padding - bottom_padding  # Space for the dotted line

    # Calculate the height of the filled bar based on the number of menu items
    bar_height = int(available_height / total_items)

    # Calculate the position of the filled bar (centered along the dotted line)
    scroll_position = top_padding + int((selected / (total_items - 1)) * (available_height - bar_height))

    # Draw the dotted scroll line (right side of the display, nudged by 2 pixels to the right)
    for y in range(top_padding, total_height - bottom_padding, 4):  # Dots every 4 pixels
        draw.point((oled.width - bar_width + 2, y), fill=255)  # Nudge the dotted line 2 pixels to the right

    # Draw the filled scroll bar for the current selection (not nudged)
    draw.rectangle((oled.width - bar_width, scroll_position, oled.width, scroll_position + bar_height), fill=255)

# Display the menu and handle navigation

def display_menu(selected):
    """Display the menu with the current selected option."""
    oled.fill(0)
    image = Image.new("1", (oled.width, oled.height))
    draw = ImageDraw.Draw(image)

    # Show the option above, the selected option (larger), and the one below, moving up for space
    options = [
        menu_options[selected - 1] if selected > 0 else menu_options[-1],  # Loop around the top
        menu_options[selected],
        menu_options[selected + 1] if selected < len(menu_options) - 1 else menu_options[0]  # Loop around the bottom
    ]

    draw.text((0, 0), options[0], font=font, fill=255)  # Option above
    draw.text((0, 14), "> " + options[1], font=large_font, fill=255)  # Selected option moved up 6 pixels
    draw.text((0, 34), options[2], font=font, fill=255)  # Third option moved up for space

    # Draw labels for the OK and Back buttons at the bottom
    ok_text = "OK"
    bbox = draw.textbbox((0, 0), ok_text, font=font)
    ok_width = bbox[2] - bbox[0]  # Calculate the width of the text
    draw.text((oled.width - ok_width - 5, 50), ok_text, font=font, fill=255)  # Right-align OK
    draw.text((0, 50), "Back", font=font, fill=255)

    # Draw the scroll bar
    draw_scroll_bar(draw, selected, len(menu_options))

    # Update the OLED display
    oled.image(image)
    oled.show()

# Main menu navigation logic without animation

# Function to display the main menu (hidden cycle behavior, larger selected text with spacing)
def display_menu(current_selection):
    """Display the main menu options with larger selected text and no Back button."""
    oled.fill(0)
    image = Image.new("1", (oled.width, oled.height))
    draw = ImageDraw.Draw(image)

    menu_options = ["Today", "Log Event", "Contacts"]

    # Use different font sizes for the selected and non-selected options
    small_font = ImageFont.truetype("DejaVuSans.ttf", 12)  # Small font for non-selected items
    large_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 16)  # Larger font for the selected item

    # Spacing around the selected item
    selected_y_position = 20  # Slightly lower to give space for OK at the bottom
    non_selected_y_offset = 18  # Y position offset for non-selected items

    # Display the previous option (smaller text)
    if current_selection > 0:  # If not the first item
        draw.text((0, selected_y_position - non_selected_y_offset), menu_options[current_selection - 1], font=small_font, fill=255)

    # Display the current selection with larger text and space around it
    draw.text((0, selected_y_position), "> " + menu_options[current_selection], font=large_font, fill=255)

    # Display the next option (smaller text)
    if current_selection < len(menu_options) - 1:  # If not the last item
        draw.text((0, selected_y_position + non_selected_y_offset + 2), menu_options[current_selection + 1], font=small_font, fill=255)

    # Draw only the OK label since Back is not needed
    draw.text((oled.width - 25, oled.height - 12), "OK", font=small_font, fill=255)

    oled.image(image)
    oled.show()


# Main Menu function with hidden cycle behavior and larger selected text with spacing
def main_menu():
    global current_selection
    current_selection = 0  # Starting position

    display_menu(current_selection)  # Ensure the menu is drawn when returning to it

    while True:
        if GPIO.input(UP_BUTTON_PIN) == GPIO.LOW:  # Move selection up
            if current_selection > 0:  # Don't visually cycle up past the first item
                current_selection -= 1
            else:
                current_selection = len(menu_options) - 1  # Wrap around to last option
            display_menu(current_selection)
            time.sleep(0.3)  # Debounce

        if GPIO.input(DOWN_BUTTON_PIN) == GPIO.LOW:  # Move selection down
            if current_selection < len(menu_options) - 1:
                current_selection += 1
            else:
                current_selection = 0  # Wrap around to the first option
            display_menu(current_selection)
            time.sleep(0.3)  # Debounce

        if GPIO.input(CONFIRM_BUTTON_PIN) == GPIO.LOW:  # OK button pressed
            selected_option = menu_options[current_selection]
            if selected_option == "Today":
                today_menu()  # Call the Today menu
                display_menu(current_selection)  # Redraw main menu when coming back from Today
            elif selected_option == "Log Event":
                log_event_menu()  # Call the Log Event menu
                display_menu(current_selection)  # Redraw main menu when coming back from Log Event
            elif selected_option == "Contacts":
                contacts_menu()  # Call the Contacts menu
                display_menu(current_selection)  # Redraw main menu when coming back from Contacts
            time.sleep(0.3)  # Debounce

        if GPIO.input(BACK_BUTTON_PIN) == GPIO.LOW:  # Back button pressed
            print("Already in main menu")  # No Back needed on main menu
            display_menu(current_selection)  # Always redraw when Back is pressed to ensure the main menu appears
            time.sleep(0.3)  # Debounce

def today_menu():
    """Display today's contacts and allow navigation."""
    contacts = get_today_contacts()  # This will get the contacts for today
    
    if not contacts:
        print("No contacts available for today.")
        return
    
    current_selection = 0
    display_today_menu(contacts, current_selection)

    while True:
        if GPIO.input(UP_BUTTON_PIN) == GPIO.LOW:  # Scroll up
            current_selection = (current_selection - 1) % len(contacts)
            display_today_menu(contacts, current_selection)
            time.sleep(0.3)  # Debounce

        if GPIO.input(DOWN_BUTTON_PIN) == GPIO.LOW:  # Scroll down
            current_selection = (current_selection + 1) % len(contacts)
            display_today_menu(contacts, current_selection)
            time.sleep(0.3)  # Debounce

        if GPIO.input(BACK_BUTTON_PIN) == GPIO.LOW:  # Back button pressed
            print("Back to main menu")
            return  # Return to the previous screen (Main Menu)


def display_today_menu(contacts, current_selection):
    """Display the contacts for today in a scrollable menu."""
    oled.fill(0)
    image = Image.new("1", (oled.width, oled.height))
    draw = ImageDraw.Draw(image)

    # Display the current contact and surrounding contacts
    if len(contacts) > 0:
        options = [
            contacts[current_selection - 1][1] if current_selection > 0 else contacts[-1][1],  # Previous contact
            contacts[current_selection][1],  # Current selected contact
            contacts[current_selection + 1][1] if current_selection < len(contacts) - 1 else contacts[0][1]  # Next contact
        ]

        draw.text((0, 0), options[0], font=font, fill=255)  # Previous contact
        draw.text((0, 14), "> " + options[1], font=font, fill=255)  # Current selected contact
        draw.text((0, 28), options[2], font=font, fill=255)  # Next contact
    else:
        draw.text((0, 14), "No contacts today!", font=font, fill=255)

    # Draw labels for Back and OK buttons at the bottom
    draw.text((oled.width - 25, oled.height - 10), "OK", font=font, fill=255)
    draw.text((0, oled.height - 10), "Back", font=font, fill=255)

    # Update the OLED display
    oled.image(image)
    oled.show()
    
    
    
def display_contacts_menu(contacts, current_selection):
    """Display the list of contacts for selection."""
    oled.fill(0)
    image = Image.new("1", (oled.width, oled.height))
    draw = ImageDraw.Draw(image)

    if len(contacts) > 0:
        options = [
            contacts[current_selection - 1][1] if current_selection > 0 else contacts[-1][1],  # Previous contact
            contacts[current_selection][1],  # Current selected contact
            contacts[current_selection + 1][1] if current_selection < len(contacts) - 1 else contacts[0][1]  # Next contact
        ]

        draw.text((0, 0), options[0], font=font, fill=255)  # Previous contact
        draw.text((0, 14), "> " + options[1], font=font, fill=255)  # Current selected contact
        draw.text((0, 28), options[2], font=font, fill=255)  # Next contact
    else:
        draw.text((0, 14), "No contacts available", font=font, fill=255)

    # Draw labels for Back and OK buttons
    draw.text((oled.width - 25, oled.height - 10), "OK", font=font, fill=255)
    draw.text((0, oled.height - 10), "Back", font=font, fill=255)

    oled.image(image)
    oled.show()

# Function to display the event type selection menu
def display_event_type_selection(event_types, current_selection):
    """Display the list of event types for selection."""
    oled.fill(0)
    image = Image.new("1", (oled.width, oled.height))
    draw = ImageDraw.Draw(image)

    # Display the event types
    options = [
        event_types[current_selection - 1] if current_selection > 0 else event_types[-1],
        event_types[current_selection],  # Current selection
        event_types[current_selection + 1] if current_selection < len(event_types) - 1 else event_types[0]
    ]

    draw.text((0, 0), options[0], font=font, fill=255)  # Previous event type
    draw.text((0, 14), "> " + options[1], font=font, fill=255)  # Current selected event type
    draw.text((0, 28), options[2], font=font, fill=255)  # Next event type

    # Draw labels for Back and OK buttons
    draw.text((oled.width - 25, oled.height - 10), "OK", font=font, fill=255)
    draw.text((0, oled.height - 10), "Back", font=font, fill=255)

    oled.image(image)
    oled.show()

# Function to display the rating selection menu
def display_event_rating_selection(ratings, current_selection):
    """Display the list of ratings for selection."""
    oled.fill(0)
    image = Image.new("1", (oled.width, oled.height))
    draw = ImageDraw.Draw(image)

    # Display the ratings
    options = [
        str(ratings[current_selection - 1]) if current_selection > 0 else str(ratings[-1]),
        str(ratings[current_selection]),  # Current selection
        str(ratings[current_selection + 1]) if current_selection < len(ratings) - 1 else str(ratings[0])
    ]

    draw.text((0, 0), options[0], font=font, fill=255)  # Previous rating
    draw.text((0, 14), "> " + options[1], font=font, fill=255)  # Current selected rating
    draw.text((0, 28), options[2], font=font, fill=255)  # Next rating

    # Draw labels for Back and OK buttons
    draw.text((oled.width - 25, oled.height - 10), "OK", font=font, fill=255)
    draw.text((0, oled.height - 10), "Back", font=font, fill=255)

    oled.image(image)
    oled.show()
    
    
    
######################### LOG EVENT FLOW AND UI #################################
    
# Function to display the "Event logged :)" message
def display_event_logged_screen():
    """Show confirmation that the event was logged successfully."""
    oled.fill(0)
    image = Image.new("1", (oled.width, oled.height))
    draw = ImageDraw.Draw(image)

    # Display the message
    draw.text((oled.width // 4, oled.height // 2 - 10), "Event logged :)", font=font, fill=255)

    # Update the OLED display
    oled.image(image)
    oled.show()

    # Display for 1 second
    time.sleep(1)

# Function to display the contact selection menu (alphabetized, no visual roundabout)
def display_contacts_menu(contacts, current_selection):
    """Display the list of contacts for selection, sorted alphabetically."""
    contacts.sort(key=lambda x: x[1])  # Sort contacts alphabetically by name
    oled.fill(0)
    image = Image.new("1", (oled.width, oled.height))
    draw = ImageDraw.Draw(image)

    # Display the list of contacts without showing the visual cycling
    options = [
        contacts[current_selection - 1][1] if current_selection > 0 else "",  # Previous contact (blank if first)
        contacts[current_selection][1],  # Current selected contact
        contacts[current_selection + 1][1] if current_selection < len(contacts) - 1 else ""  # Next contact (blank if last)
    ]

    # Display the menu options
    if options[0]:  # Show only if it's not empty
        draw.text((0, 0), options[0], font=font, fill=255)
    draw.text((0, 14), "> " + options[1], font=font, fill=255)  # Highlighted current selection
    if options[2]:  # Show only if it's not empty
        draw.text((0, 28), options[2], font=font, fill=255)

    # Draw labels for Back and OK buttons at the bottom
    draw.text((oled.width - 25, oled.height - 10), "OK", font=font, fill=255)
    draw.text((0, oled.height - 10), "Back", font=font, fill=255)

    oled.image(image)
    oled.show()

# Main Log Event flow
def log_event_menu():
    """Start the Log Event flow."""
    contacts = get_all_contacts()  # Fetch the contacts from the database
    event_types = ["Email", "Phone Call", "In-person"]
    ratings = [1, 2, 3, 4, 5]
    
    if not contacts:
        print("No contacts available.")
        return

    # Sort contacts alphabetically
    contacts.sort(key=lambda x: x[1])  # Sort by name

    current_screen = 1  # Track which screen we are on (1: Contact, 2: Type, 3: Rating)
    current_selection = 0  # Initial selection

    # First screen: Select WHO the contact event was with
    display_contacts_menu(contacts, current_selection)

    while True:
        if GPIO.input(UP_BUTTON_PIN) == GPIO.LOW:  # Scroll up
            if current_screen == 1:  # Contact selection screen
                current_selection = (current_selection - 1) % len(contacts)
                display_contacts_menu(contacts, current_selection)
            elif current_screen == 2:  # Event type selection screen
                current_selection = (current_selection - 1) % len(event_types)
                display_event_type_selection(event_types, current_selection)
            elif current_screen == 3:  # Rating selection screen
                current_selection = (current_selection - 1) % len(ratings)
                display_event_rating_selection(ratings, current_selection)
            time.sleep(0.3)  # Debounce

        if GPIO.input(DOWN_BUTTON_PIN) == GPIO.LOW:  # Scroll down
            if current_screen == 1:
                current_selection = (current_selection + 1) % len(contacts)
                display_contacts_menu(contacts, current_selection)
            elif current_screen == 2:
                current_selection = (current_selection + 1) % len(event_types)
                display_event_type_selection(event_types, current_selection)
            elif current_screen == 3:
                current_selection = (current_selection + 1) % len(ratings)
                display_event_rating_selection(ratings, current_selection)
            time.sleep(0.3)  # Debounce

        if GPIO.input(CONFIRM_BUTTON_PIN) == GPIO.LOW:  # OK button pressed
            if current_screen == 1:  # Contact selection screen
                selected_contact = contacts[current_selection]
                print(f"Selected contact: {selected_contact[1]}")
                current_screen = 2  # Move to the next screen (Event Type)
                current_selection = 0  # Reset selection for next screen
                display_event_type_selection(event_types, current_selection)
            elif current_screen == 2:  # Event type selection screen
                event_type = event_types[current_selection]
                print(f"Selected event type: {event_type}")
                current_screen = 3  # Move to the next screen (Rating)
                current_selection = 0  # Reset selection for next screen
                display_event_rating_selection(ratings, current_selection)
            elif current_screen == 3:  # Rating selection screen
                event_rating = ratings[current_selection]
                print(f"Selected rating: {event_rating}")
                log_event_to_db(selected_contact[0], event_type, event_rating)  # Log the event
                display_event_logged_screen()  # Show confirmation screen
                time.sleep(0.3)  # Debounce
                return  # Exit after logging the event and showing confirmation

        if GPIO.input(BACK_BUTTON_PIN) == GPIO.LOW:  # Back button pressed
            if current_screen == 3:  # If on Rating screen, go back to Event Type screen
                current_screen = 2
                display_event_type_selection(event_types, current_selection)
            elif current_screen == 2:  # If on Event Type screen, go back to Contact Selection screen
                current_screen = 1
                display_contacts_menu(contacts, current_selection)
            elif current_screen == 1:  # If on Contact Selection, go back to Main Menu and cancel
                print("Back to main menu, event canceled")
                return  # Exit to main menu and cancel the event
            time.sleep(0.3)  # Debounce
    
    
    
    
    

if __name__ == "__main__":
    main_menu()
    
    
