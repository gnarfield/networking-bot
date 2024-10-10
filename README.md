this project is all about creating a device that externalizes my memory and helps me remember to contact people and maintain relationships with them.

HARDWARE
- Raspberry Pi Zero 2W
- OLED display (128x64)
- four buttons


Every day, the DEVICE generates a TODAY list by pulling three random contacts from the CONTACTABLE list. 
The CONTACTABLE list is a list of contacts whose FREQUENCY number has been exceeded by the delta between their LAST_CONTACTED_DATE and today's date.
When interaction has occurred with a contact, we call this a CONTACT EVENT.
