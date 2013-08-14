import gevent.monkey
gevent.monkey.patch_all()

import gevent
from gevent import wsgi

import urlparse

import json
import requests
import re
from pprint import pprint

BIND='localhost'
PORT=8787
ASANA_BASE_URL = 'https://app.asana.com/api/1.0'
# Don't forget to add the colon to the API key
# echo -n "<API key from Asana settings>:" | openssl enc -base64
ASANA_KEY = ""
ASANA_HEADERS= {"Authorization":"Basic %s"%ASANA_KEY}

def normalize_verb(s):
    s = s.lower()
    if any(w in s for w in ('fixing', 'fixes', 'fixed', 'fix', 'close', 'closed', 'closes')):
        return 'fix'
    elif any(w in s for w in ('addressing', 'referencing', 'addresses', 're', 'ref', 'references', 'see')):
        return 'see'
    elif any(w in s for w in ('breaking', 'breaks', 'unfixes', 'reopen', 'reopens', 're-opens', 're-open')):
        return 'break'

def get_task_actions(commits):
    tasks = []
    for commit in commits:
        regex_verb = re.compile(r'(Referencing|Addressing|References|Addresses|Reopening|Re-opening|Re-opens|Breaking|Unfixes|Unfixing|Reopens|Re-open|Fixing|Closes|Closing|Closed|Breaks|Reopen|Fixed|Close|Fixes|Refs|Ref|Fix|See|Re)', flags=re.IGNORECASE)
        regex_id   = re.compile(r'#(\d+)',flags=re.IGNORECASE)
        regex_stop = re.compile(r'\w(\.)',flags=re.IGNORECASE)
        words    = commit['message'].split(" ")
        current_verb = ''
        current_id   = ''
        updated_verb_or_id = False # used to flag when we really ought to push values to the task list

        for word in words:
            sub_words = word.split(",") # Retrieves words split by commas
            for sub_word in sub_words:
                # Match verbs/ids out of individual words
                cid = regex_id.findall(sub_word);
                verb = regex_verb.findall(sub_word);
                stop = regex_stop.findall(sub_word);
                
                if cid:
                    current_id = cid[0]
                    updated_verb_or_id = True
                    
                    # For every matched ID, we attach a 'see' task so there is always a comment (regardless of verbs)
                    tasks.append({
                        "verb":'see',
                        "id":current_id,
                        "message":commit['author']['username'] + ' referenced this issue from a commit\n'+commit['id'][:7]+' '+commit['message']+'\n'+commit['url']
                    });
                elif verb:
                    current_verb = verb[0]
                    current_id = '' # We reset the current_id here because a new verb is in play
                    updated_verb_or_id = True
                if current_id and current_verb and updated_verb_or_id:
                    if 'see' not in normalize_verb(current_verb):  # We already track every ID with a 'see' verb above
                        tasks.append({
                            "verb":normalize_verb(current_verb),
                            "id":current_id
                        });
                    updated_verb_or_id = False # Don't push another element until it is unique
                
                if stop: # When we encounter a word that ends with a period, reset.
                    current_verb = ''
                    current_id = ''
                    updated_verb_or_id = False
    return tasks

def send_task_comments_to_asana(tasks):
    for task in tasks:
        url = "%s/%s/%s"%(ASANA_BASE_URL,'tasks',task['id'])
        method = requests.put
        if task['verb']=='fix':
            payload = {"completed":True}
        elif task['verb']=='break':
            payload = {"completed":False}
        elif task['verb']=='see':
            url = "%s/stories"%url
            payload = {"text":task['message']}
            method = requests.post
        print "[*] Making request to: %s"%url
        print "[-]   data: %s"%payload
        response = method(url,data=payload,headers=ASANA_HEADERS)
        print "[*] ASANA RESPONSE"
        pprint(response.json)

def index(environ,start_response):
    start_response('200 OK', [('Content-Type', 'application/json')])

    parsed_input = urlparse.parse_qs(environ['wsgi.input'].read())

    if parsed_input.has_key("payload"):
        body = parsed_input["payload"][0]
        commits = json.loads(body)['commits']
        actions  = get_task_actions(commits)
        send_task_comments_to_asana(actions)
        return [ '{ "success" : true }\n' ]
    return [ '{ "success" : false }\n' ]

print "[*] Serving %s to port %d"%(BIND,PORT)

server = wsgi.WSGIServer(
    (BIND,PORT), index)
server.serve_forever()
