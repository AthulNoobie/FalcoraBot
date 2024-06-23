import google.generativeai as genai
from flask import Flask,request,jsonify,render_template
import requests
import os
import fitz

wa_token=os.environ.get("WA_TOKEN") # Whatsapp API Key
genai.configure(api_key=os.environ.get("GEN_API")) # Gemini API Key
owner_phone=os.environ.get("OWNER_PHONE") # Owner's phone number with +countrycode
model_name="gemini-1.5-flash-latest"

app=Flask(__name__)

generation_config = {
  "temperature": 1,
  "top_p": 0.95,
  "top_k": 0,
  "max_output_tokens": 8192,
}

safety_settings = [
  {"category": "HARM_CATEGORY_HARASSMENT","threshold": "BLOCK_MEDIUM_AND_ABOVE"},
  {"category": "HARM_CATEGORY_HATE_SPEECH","threshold": "BLOCK_MEDIUM_AND_ABOVE"},  
  {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT","threshold": "BLOCK_MEDIUM_AND_ABOVE"},
  {"category": "HARM_CATEGORY_DANGEROUS_CONTENT","threshold": "BLOCK_MEDIUM_AND_ABOVE"},
]

model = genai.GenerativeModel(model_name=model_name,
                              generation_config=generation_config,
                              safety_settings=safety_settings)

convo = model.start_chat(history=[
])

with open("instructions.txt","r") as f:
    commands=f.read()
convo.send_message(commands)

def send(answer,sender,phone_id):
    url=f"https://graph.facebook.com/v18.0/{phone_id}/messages"
    headers={
        'Authorization': f'Bearer {wa_token}',
        'Content-Type': 'application/json'
    }
    data={
          "messaging_product": "whatsapp", 
          "to": f"{sender}", 
          "type": "text",
          "text":{"body": f"{answer}"},
          }
    
    response=requests.post(url, headers=headers,json=data)
    return response

def remove(*file_paths):
    for file in file_paths:
        if os.path.exists(file):
            os.remove(file)
        else:pass

@app.route("/", methods=["GET", "POST"])
def index():
    return render_template("connected.html")

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if mode == "subscribe" and token == "BOT":
            return challenge, 200
        else:
            return "Failed", 403
    elif request.method == "POST":
        try:
            data = request.get_json()["entry"][0]["changes"][0]["value"]["messages"][0]
            phone_id=request.get_json()["entry"][0]["changes"][0]["value"]["metadata"]["phone_number_id"]
            sender="+"+data["from"]
            if data["type"] == "text":
                prompt = data["text"]["body"]
                convo.send_message(prompt)
            else:
                media_url_endpoint = f'https://graph.facebook.com/v18.0/{data[data["type"]]["id"]}/'
                headers = {'Authorization': f'Bearer {wa_token}'}
                media_response = requests.get(media_url_endpoint, headers=headers)
                media_url = media_response.json()["url"]
                media_download_response = requests.get(media_url, headers=headers)
                if data["type"] == "audio":
                    filename = "/tmp/temp_audio.mp3"
                elif data["type"] == "image":
                    filename = "/tmp/temp_image.jpg"
                elif data["type"] == "document":
                    doc=fitz.open(stream=media_download_response.content,filetype="pdf")
                    for _,page in enumerate(doc):
                        destination="/tmp/temp_image.jpg"
                        pix = page.get_pixmap()
                        pix.save(destination)
                        file = genai.upload_file(path=destination,display_name="tempfile")
                        response = model.generate_content(["What is this",file])
                        answer=response._result.candidates[0].content.parts[0].text
                        convo.send_message(f'''Direct image input has limitations,
                                           so this message is created by an llm model based on the image prompt of user, 
                                            reply to the customer assuming you saw that image 
                                           (Warn the customer and stop the chat if it is not related to the business): {answer}''')
                        remove(destination)
                else:send("This format is not Supported by the bot ☹",sender,phone_id)
                if data["type"] == "image" or data["type"] == "audio":
                    with open(filename, "wb") as temp_media:
                        temp_media.write(media_download_response.content)
                    file = genai.upload_file(path=filename,display_name="tempfile")
                    response = model.generate_content(["What is this",file])
                    answer=response._result.candidates[0].content.parts[0].text
                    remove("/tmp/temp_image.jpg","/tmp/temp_audio.mp3")
                    convo.send_message(f'''Direct media input has limitations,
                                            so this message is created by an llm model based on the image prompt of user, 
                                            reply to the customer assuming you saw that image 
                                            (Warn the customer and stop the chat if it is not related to the business): {answer}''')
                files=genai.list_files()
                for file in files:
                    file.delete()
            reply=convo.last.text
            if "unable_to_solve_query" in reply:
                send(f"customer {sender} is not satisfied",owner_phone,phone_id)
                send("Our agent will contact you shortly.",sender,phone_id)
            else:send(reply,sender,phone_id)
        except :pass
        return jsonify({"status": "ok"}), 200
    else:return "WhatsApp Bot is Running"
if __name__ == "__main__":
    app.run(debug=True, port=8000)