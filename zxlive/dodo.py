# DODO-GPT is brought to you by Dave the Dodo of Picturing Quantum Processes fame

import pyzx as zx
import openai
import sounddevice as sd
import os
import numpy as np
import base64
import requests
from pydub import AudioSegment
from .utils import GET_MODULE_PATH
from enum import IntEnum

API_KEY = 'no-key'

# Need to add error handling still! (e.g. if invalid key, or if no connection to chat-gpt server, etc.)
# Maybe add a config (i.e. to set the api_key, the gpt model, the OpenAI Whisper voice, etc.)
# Maybe also record your full transripts with DODO-GPT (and have the option of whether to save it to file when you close zxlive)

#TEMP... (# TEMP - this should just be calling xz.utils.VertexType instead (not sure why that doesn't work though?): VertexType(1).name)
class VertexType(IntEnum):
    """Type of a vertex in the graph."""
    BOUNDARY = 0
    Z = 1
    X = 2
    H_BOX = 3
    W_INPUT = 4
    W_OUTPUT = 5
    Z_BOX = 6
    
#TEMP... (# TEMP - this should just be calling xz.utils.VertexType instead (not sure why that doesn't work though?): VertexType(1).name)
class EdgeType(IntEnum):
    """Type of an edge in the graph."""
    SIMPLE = 1
    HADAMARD = 2
    W_IO = 3

def get_local_api_key():
    """Get the API key from key.txt file"""
    f = open(GET_MODULE_PATH()+"/user/key.txt", "r")
    global API_KEY
    API_KEY = f.read()
    f.close()

def query_chatgpt(prompt,model="gpt-3.5-turbo"):
    """Send a prompt to Chat-GPT and return its response."""
    client = openai.OpenAI(
        api_key = API_KEY
    )
    
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role":"user",
                "content":prompt
            }
        ],
        model=model#"gpt-3.5-turbo"#"gpt-4o"
    )
    return chat_completion.choices[0].message.content

def prep_hint(g):
    """Generate the default/generic 'ask for hint' type prompt for DODO-GPT."""
    strPrime = describe_graph(g)
    strQuery = strPrime + "Please advise me as to what ONE simplification step I should take to help immediately simplify this ZX-diagram. Please be specific to this case and not give general simplification tips. Please also keep your answer simple and do not write any diagrams or data in return."
    return strQuery

def describe_graph(g):
    """Prime DODO-GPT before making a query. Returns a string for describing to DODO-GPT the current ZX-diagram."""
    
    VertexType = {0:'BOUNDARY',1:'Z',2:'X'}
    EdgeType   = {1:'SIMPLE',2:'HADAMARD'}
    
    strPrime = "\nConsider a ZX-diagram defined by the following spiders:\n\nlabel, type, phase\n"
    for v in g.vertices(): strPrime += str(v) + ', ' + str(VertexType[g.type(v)]) + ', ' + str(g.phase(v)) + '\n'
    
    strPrime += "\nwith the following edges:\n\nsource,target,type\n"
    for e in g.edges(): strPrime += str(e[0]) + ', ' + str(e[1]) + ', ' + str(EdgeType[g.edge_type(e)]) + '\n'
    strPrime += '\n'
    
    #Follows the format...
    #
    #"""
    #Consider a ZX-diagram defined by the following spiders:
    #
    #label, type, phase
    #0, Z, 0.25
    #1, Z, 0.5
    #2, X, 0.5
    #
    #with the following edges:
    #
    #source,target,type
    #0, 1, SIMPLE
    #1, 2, HADAMARD
    #
    #"""
    
    return strPrime

def text_to_speech(text):
    """Generates an mp3 file reading the given text (via OpenAI Whisper)."""
    client = openai.OpenAI(
        api_key = API_KEY
    )

    response = client.audio.speech.create(
        model="tts-1",
        voice="nova",
        input=text,
    )
    
    response.stream_to_file(GET_MODULE_PATH() + "/temp/Dodo_Dave_latest.mp3")
    os.system(GET_MODULE_PATH() + "/temp/Dodo_Dave_latest.mp3") #TEMP/TODO - THIS SHOULD BE USING A PROPER IN-APP AUDIO PLAYER RATHER THAN OS

def record_audio(duration=5, sample_rate=44100):
    recording = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=2, dtype='int16')
    sd.wait()
    return recording

def save_as_mp3(audio_data, sample_rate=44100):
    file_path = GET_MODULE_PATH() + "/temp/user_query_latest.mp3"
    audio_segment = AudioSegment(
        data=np.array(audio_data).tobytes(),
        sample_width=2,
        frame_rate=sample_rate,
        channels=2
    )
    audio_segment.export(file_path, format='mp3')
    return file_path

def transcribe_audio(file_path):
    client = openai.OpenAI(api_key=API_KEY)
    with open(file_path, "rb") as audio_file:
        transcription = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language='en'
        )
    #print(f'Transcription: {transcription.text}') #TEMP
    return transcription.text

def speech_to_text():
    sample_rate = 44100  # Sample rate in Hz
    duration = 5  # Duration of recording in seconds
    audio_data = record_audio(duration, sample_rate)
    file_path = save_as_mp3(audio_data, sample_rate)
    txt = transcribe_audio(file_path)
    return txt

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')
        
def get_image_prompt():
    """Returns the prompt that encourages DODO-GPT to describe the given image like a ZX-diagram."""

    return """
    Please convert this image into a ZX-diagram.

    Then please provide a csv that lists of the spiders of this ZX-diagram, given the column headers:
    index,type,phase,x-pos,y-pos

    The type here should be given as either 'Z' or 'X' (ignore boundary spiders). The indexing should start from 0. And the phases should be written in terms of pi. x-pos and y-pos should respectively refer to their horizontal and vertical positions in the image, normalized from 0,0 (top-left) to 1,1 (bottom-right).

    Then please provide a csv that lists the edges of this ZX-diagram, given the column headers:
    source,target,type

    The type here should be given as 1 for a normal (i.e. black) edge and 2 for a Hadamard (i.e. blue) edge, and the sources and targets should refer to the indices of the relevant spiders. Be sure to only include direct edges connecting two spiders.

    Please ensure the csv's are expressed with comma separators and not in a table format.
    """
    #After that, under a clearly marked heading "HINT", please advise me as to what ONE simplification step I should take to help immediately simplify this ZX-diagram. Please be specific to this case and not give general simplification tips.
    #"""
        
def image_to_text(image_path):
    """Takes a ZX-diagram-like image and returns DODO-GPT's structured description of it."""
    
    query = get_image_prompt()

    # Getting the base64 string
    base64_image = encode_image(image_path)

    headers = {
      "Content-Type": "application/json",
      "Authorization": f"Bearer {API_KEY}"
    }

    payload = {
      "model": "gpt-4o-mini",
      "messages": [
        {
          "role": "user",
          "content": [
            {
              "type": "text",
              "text": query
            },
            {
              "type": "image_url",
              "image_url": {
                "url": f"data:image/jpeg;base64,{base64_image}"
              }
            }
          ]
        }
      ],
      "max_tokens": 300
    }

    response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)

    #return response.json()
    return response.json()['choices'][0]['message']['content']

def response_to_zx(strResponse):
    scale = 2.5
    
    strResponse    = strResponse
    strResponse    = strResponse[strResponse.index('index,type,phase'):]
    strResponse    = strResponse[strResponse.index('\n')+1:]
    str_csv_verts  = strResponse[:strResponse.index('```')-1]
    strResponse    = strResponse[strResponse.index('source,target,type'):]
    strResponse    = strResponse[strResponse.index('\n')+1:]
    str_csv_edges  = strResponse[:strResponse.index('```')-1]
    
    g = zx.Graph()
    
    for line in str_csv_verts.split('\n'):
        idx,ty,ph,x,y = line.split(',')
        g.add_vertex(qubit=float(y)*scale,row=float(x)*scale,ty=VertexType[ty],phase=ph)
    
    for line in str_csv_edges.split('\n'):
        source,target,ty = line.split(',')
        g.add_edge((int(source),int(target)),int(ty))
    
    return g

def action_dodo_hint(active_graph) -> None:
    """Queries DODO-GPT for a hint as to what simplification step should be taken next."""
    #print("\n\nQUERY...\n\n", prep_hint(active_graph), "\n\nANSWER...\n\n") #TEMP
    dodoResponse = query_chatgpt(prep_hint(active_graph))
    #print(dodoResponse) #TEMP
    text_to_speech(dodoResponse)

def action_dodo_query(active_graph) -> None:
    """Records the user's voice (plus the current ZX-diagram) and prompts DODO-GPT for a response."""
    doIncludeGraph = True # Whether or not to pass information about the current ZX-diagram in with the DODO-GPT query
    strPrime = describe_graph(active_graph)
    userQuery = speech_to_text()
    #print("\n\nQUERY...\n\n", strPrime+userQuery, "\n\nANSWER...\n\n") #TEMP
    dodoResponse = query_chatgpt(strPrime+userQuery)
    #print(dodoResponse) #TEMP
    text_to_speech(dodoResponse)
    
def action_dodo_image_to_zx(path) -> None:
    """Queries DODO-GPT to generate a ZX-diagram from an image."""
    strResponse = image_to_text(path)
    #print(strResponse) #TEMP
    new_graph = response_to_zx(strResponse)
    return new_graph
