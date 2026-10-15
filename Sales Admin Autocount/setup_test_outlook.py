import msal, httpx, os

CLIENT_ID = os.getenv("MS_CLIENT_ID")
AUTHORITY = "https://login.microsoftonline.com/consumers"   # personal; use your tenant ID for work accounts
SCOPES = ["Mail.Read"]

cache = msal.SerializableTokenCache()
if os.path.exists("token_cache.json"):
    cache.deserialize(open("token_cache.json").read())

app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY, token_cache=cache)

accounts = app.get_accounts()
result = app.acquire_token_silent(SCOPES, account=accounts[0]) if accounts else None
if not result:
    flow = app.initiate_device_flow(scopes=SCOPES)
    print(flow["message"])                      # open the link, enter the code, sign in
    result = app.acquire_token_by_device_flow(flow)

open("token_cache.json", "w").write(cache.serialize())

r = httpx.get(
    "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages",
    headers={
        "Authorization": f"Bearer {result['access_token']}",
        "Prefer": 'outlook.body-content-type="text"',
    },
    params={
        "$top": 10,
        "$orderby": "receivedDateTime desc",
        "$select": "id,subject,from,replyTo,receivedDateTime,hasAttachments,body,internetMessageHeaders",
    },
)
for m in r.json().get("value", []):
    print(m["receivedDateTime"], m["from"]["emailAddress"]["address"], "|", m["subject"])