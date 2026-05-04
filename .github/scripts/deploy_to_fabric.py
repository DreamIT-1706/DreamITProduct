import os
import requests
import time
import json
import base64

# ============================================================================
# CONFIGURATION - Environment Variables
# ============================================================================

TENANT_ID = os.environ['TENANT_ID']
CLIENT_ID = os.environ['CLIENT_ID']
CLIENT_SECRET = os.environ['CLIENT_SECRET']

TARGET_TENANT_ID = os.environ['TARGET_TENANT_ID']

WORKSPACE_ID = os.environ.get('WORKSPACE_ID')
WORKSPACE_NAME = os.environ.get('WORKSPACE_NAME')
CAPACITY_ID = os.environ.get('CAPACITY_ID')
ADMIN_USERS = os.environ.get('ADMIN_USERS', '')
MODULES = os.environ.get('MODULES', 'BusinessCentral')

BASE_URL = "https://api.fabric.microsoft.com/v1"

# ============================================================================
# AUTHENTICATION (Cross-Tenant)
# ============================================================================

def get_access_token(scope="https://api.fabric.microsoft.com/.default", target_tenant=None):
    tenant_id = target_tenant or TARGET_TENANT_ID
    is_cross_tenant = tenant_id != TENANT_ID
    tenant_name = "Client (Target)" if is_cross_tenant else "Dream IT (Home)"

    print(f"🔐 Getting access token...")
    print(f"   Tenant: {tenant_name} ({tenant_id})")

    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    token_data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": scope,
        "grant_type": "client_credentials"
    }

    try:
        response = requests.post(token_url, data=token_data)
        response.raise_for_status()
        token = response.json()["access_token"]
        print("✅ Token acquired successfully")
        return token
    except requests.exceptions.HTTPError as e:
        print(f"❌ Token acquisition failed: {e}")
        print(f"   Response: {e.response.text}")
        if e.response.status_code == 401:
            print("\n💡 Troubleshooting:")
            print("   1. Verify app is multi-tenant in Dream IT tenant")
            print("   2. Ensure admin consent granted in client tenant")
            print("   3. Check client secret is valid")
        raise

# ============================================================================
# WORKSPACE OPERATIONS
# ============================================================================

def list_all_workspaces(token):
    url = f"{BASE_URL}/workspaces"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json().get("value", [])

def find_workspace_by_name(token, workspace_name):
    workspaces = list_all_workspaces(token)
    for ws in workspaces:
        if ws.get("displayName") == workspace_name:
            return ws.get("id")
    return None

def create_workspace(token, workspace_name, capacity_id):
    print("\n" + "=" * 60)
    print("🏗️  CREATING WORKSPACE IN CLIENT TENANT")
    print("=" * 60)

    existing_id = find_workspace_by_name(token, workspace_name)
    if existing_id:
        print(f"⚠️  Workspace '{workspace_name}' already exists. Using it.")
        return existing_id

    url = f"{BASE_URL}/workspaces"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = {"displayName": workspace_name, "capacityId": capacity_id}

    response = requests.post(url, headers=headers, json=body)
    response.raise_for_status()
    workspace_id = response.json().get("id")
    print(f"✅ Workspace created: {workspace_id}")
    return workspace_id

def list_workspace_items(token, workspace_id):
    url = f"{BASE_URL}/workspaces/{workspace_id}/items"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json().get("value", [])

def check_workspace_empty(token, workspace_id):
    print("\n🔍 Checking if workspace is empty...")
    items = list_workspace_items(token, workspace_id)
    if len(items) > 0:
        print(f"❌ Workspace is NOT empty! Found {len(items)} item(s):")
        for item in items:
            print(f"   - {item['displayName']} ({item['type']})")
        print("\n💡 Please empty the workspace before deploying.")
        return False
    print("✅ Workspace is empty - proceeding")
    return True

def add_workspace_admin_by_email(workspace_id, user_email):
    powerbi_token = get_access_token(
        scope="https://analysis.windows.net/powerbi/api/.default",
        target_tenant=TARGET_TENANT_ID
    )
    url = f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/users"
    headers = {"Authorization": f"Bearer {powerbi_token}", "Content-Type": "application/json"}
    body = {"emailAddress": user_email, "groupUserAccessRight": "Admin"}

    response = requests.post(url, headers=headers, json=body)
    if response.status_code in [200, 409]:
        print(f"   ✅ Added/already exists: {user_email}")
        return True
    else:
        print(f"   ⚠️  Failed to add {user_email}: {response.status_code} - {response.text}")
        return False

def add_workspace_admins(admin_users_string, workspace_id):
    print("\n" + "=" * 60)
    print("👥 ADDING WORKSPACE ADMINS")
    print("=" * 60)
    if not admin_users_string or not admin_users_string.strip():
        print("⚠️  No admin users provided - skipping")
        return
    emails = [e.strip() for e in admin_users_string.split(',') if e.strip()]
    for email in emails:
        add_workspace_admin_by_email(workspace_id, email)

# ============================================================================
# NOTEBOOK DEPLOYMENT
# ============================================================================

# def read_notebook_content(notebook_folder_path):
#     content_file = os.path.join(notebook_folder_path, "notebook-content.py")
#     platform_file = os.path.join(notebook_folder_path, ".platform")

#     if not os.path.exists(content_file):
#         print(f"   ⚠️  notebook-content.py not found in {notebook_folder_path}")
#         return None, None

#     with open(content_file, 'r', encoding='utf-8') as f:
#         content = f.read()

#     display_name = os.path.basename(notebook_folder_path).replace(".Notebook", "")
#     if os.path.exists(platform_file):
#         try:
#             with open(platform_file, 'r') as f:
#                 platform_data = json.load(f)
#             display_name = platform_data.get("metadata", {}).get("displayName", display_name)
#         except:
#             pass

#     encoded = base64.b64encode(content.encode('utf-8')).decode('utf-8')
#     return display_name, encoded

def read_notebook_content(notebook_folder_path):
    import re
    content_file = os.path.join(notebook_folder_path, "notebook-content.py")
    platform_file = os.path.join(notebook_folder_path, ".platform")

    if not os.path.exists(content_file):
        print(f"   ⚠️  notebook-content.py not found in {notebook_folder_path}")
        return None, None

    with open(content_file, 'r', encoding='utf-8') as f:
        raw = f.read()

    # Parse # CELL ** blocks into individual cells
    cells = []
    current_lines = []
    in_cell = False

    for line in raw.splitlines():
        if re.match(r'^# CELL \*+\s*$', line):
            if in_cell and current_lines:
                code = '\n'.join(current_lines).strip()
                if code:
                    cells.append(code)
            current_lines = []
            in_cell = True
        elif re.match(r'^# METADATA \*+\s*$', line):
            if in_cell and current_lines:
                code = '\n'.join(current_lines).strip()
                if code:
                    cells.append(code)
            current_lines = []
            in_cell = False
        elif in_cell:
            current_lines.append(line)

    # Don't forget last cell
    if in_cell and current_lines:
        code = '\n'.join(current_lines).strip()
        if code:
            cells.append(code)

    # Fallback: treat whole file as one cell
    if not cells:
        cells = [raw]

    # Build proper ipynb JSON
    notebook_cells = []
    for idx, src in enumerate(cells):
        notebook_cells.append({
            "cell_type": "code",
            "id": str(idx + 1),
            "metadata": {},
            "execution_count": None,
            "outputs": [],
            "source": src.splitlines(keepends=True)
        })

    ipynb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {
            "language_info": {"name": "python"},
            "kernelspec": {
                "display_name": "Synapse PySpark",
                "language": "Python",
                "name": "synapse_pyspark"
            },
            "trident": {"lakehouse": {}}
        },
        "cells": notebook_cells
    }

    # Get display name from .platform or folder name
    display_name = os.path.basename(notebook_folder_path).replace(".Notebook", "")
    if os.path.exists(platform_file):
        try:
            with open(platform_file, 'r') as f:
                platform_data = json.load(f)
            display_name = platform_data.get("metadata", {}).get("displayName", display_name)
        except:
            pass

    # Base64 encode the ipynb JSON
    ipynb_json = json.dumps(ipynb, ensure_ascii=False)
    encoded = base64.b64encode(ipynb_json.encode('utf-8')).decode('utf-8')
    return display_name, encoded

def deploy_notebook(token, workspace_id, display_name, encoded_content):
    print(f"\n   📓 Deploying notebook: {display_name}")

    url = f"{BASE_URL}/workspaces/{workspace_id}/items"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = {
        "displayName": display_name,
        "type": "Notebook",
        "definition": {
            "format": "ipynb",
            "parts": [
                {
                    "path": "artifact.content.ipynb",
                    "payload": encoded_content,
                    "payloadType": "InlineBase64"
                }
            ]
        }
    }

    response = requests.post(url, headers=headers, json=body)

    if response.status_code == 202:
        operation_url = response.headers.get("Location")
        print(f"      ⏳ Operation in progress...")
        if operation_url:
            return poll_long_running(token, operation_url)
        return True
    elif response.status_code == 201:
        print(f"      ✅ Notebook deployed successfully")
        return True
    else:
        print(f"      ❌ Failed: {response.status_code} - {response.text}")
        return False

def deploy_pipeline(token, workspace_id, pipeline_folder_path):
    platform_file = os.path.join(pipeline_folder_path, ".platform")
    display_name = os.path.basename(pipeline_folder_path).replace(".DataPipeline", "")

    if os.path.exists(platform_file):
        try:
            with open(platform_file, 'r') as f:
                platform_data = json.load(f)
            display_name = platform_data.get("metadata", {}).get("displayName", display_name)
        except:
            pass

    pipeline_file = None
    for fname in os.listdir(pipeline_folder_path):
        if fname.endswith('.json') or fname == 'pipeline-content.json':
            pipeline_file = os.path.join(pipeline_folder_path, fname)
            break

    print(f"\n   ⚙️  Deploying pipeline: {display_name}")

    if not pipeline_file:
        print(f"      ⚠️  No pipeline definition file found - skipping")
        return False

    with open(pipeline_file, 'r') as f:
        content = f.read()

    encoded = base64.b64encode(content.encode('utf-8')).decode('utf-8')

    url = f"{BASE_URL}/workspaces/{workspace_id}/items"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    body = {
        "displayName": display_name,
        "type": "DataPipeline",
        "definition": {
            "parts": [
                {
                    "path": "pipeline-content.json",
                    "payload": encoded,
                    "payloadType": "InlineBase64"
                }
            ]
        }
    }

    response = requests.post(url, headers=headers, json=body)
    if response.status_code in [201, 202]:
        print(f"      ✅ Pipeline deployed successfully")
        return True
    else:
        print(f"      ❌ Failed: {response.status_code} - {response.text}")
        return False

def poll_long_running(token, operation_url):
    headers = {"Authorization": f"Bearer {token}"}
    for attempt in range(30):
        response = requests.get(operation_url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            status = data.get("status")
            if status == "Succeeded":
                print(f"      ✅ Completed successfully")
                return True
            elif status == "Failed":
                print(f"      ❌ Operation failed: {data.get('error', {})}")
                return False
        time.sleep(5)
    print("      ⚠️  Operation timed out")
    return False

def deploy_module(token, workspace_id, module_name):
    print("\n" + "=" * 60)
    print(f"📦 DEPLOYING MODULE: {module_name}")
    print("=" * 60)

    module_path = module_name
    if not os.path.exists(module_path):
        print(f"❌ Module folder '{module_path}' not found in repository!")
        return False

    items = os.listdir(module_path)
    print(f"   Found {len(items)} items in {module_name}/")

    success_count = 0
    fail_count = 0

    for item_name in items:
        item_path = os.path.join(module_path, item_name)
        if not os.path.isdir(item_path):
            continue

        if item_name.endswith(".Notebook"):
            display_name, encoded_content = read_notebook_content(item_path)
            if encoded_content:
                result = deploy_notebook(token, workspace_id, display_name, encoded_content)
                success_count += 1 if result else 0
                fail_count += 0 if result else 1
                time.sleep(2)

        elif item_name.endswith(".DataPipeline"):
            result = deploy_pipeline(token, workspace_id, item_path)
            success_count += 1 if result else 0
            fail_count += 0 if result else 1
            time.sleep(2)

    print(f"\n📊 Module Summary: ✅ {success_count} deployed | ❌ {fail_count} failed")
    return fail_count == 0

# ============================================================================
# MAIN WORKFLOW
# ============================================================================

def main():
    print("=" * 60)
    print("🚀 DreamIT - Deploy Modules to Client Fabric Workspace")
    print("=" * 60)
    print(f"🏢 Dream IT Tenant: {TENANT_ID}")
    print(f"🎯 Client Tenant:   {TARGET_TENANT_ID}")
    print(f"📦 Modules:         {MODULES}")

    if not WORKSPACE_ID and not (WORKSPACE_NAME and CAPACITY_ID):
        print("\n❌ ERROR: Provide either WORKSPACE_ID or both WORKSPACE_NAME + CAPACITY_ID")
        exit(1)

    try:
        # Step 1: Cross-tenant authentication
        print("\n" + "=" * 60)
        print("STEP 1: CROSS-TENANT AUTHENTICATION")
        print("=" * 60)
        token = get_access_token(target_tenant=TARGET_TENANT_ID)

        # Step 2: Workspace setup
        print("\n" + "=" * 60)
        print("STEP 2: WORKSPACE SETUP")
        print("=" * 60)
        if WORKSPACE_ID:
            workspace_id = WORKSPACE_ID
            print(f"✅ Using existing workspace: {workspace_id}")
        else:
            workspace_id = create_workspace(token, WORKSPACE_NAME, CAPACITY_ID)
            time.sleep(5)
            if ADMIN_USERS:
                add_workspace_admins(ADMIN_USERS, workspace_id)
            token = get_access_token(target_tenant=TARGET_TENANT_ID)

        # Step 3: Pre-deployment check
        print("\n" + "=" * 60)
        print("STEP 3: PRE-DEPLOYMENT CHECK")
        print("=" * 60)
        if not check_workspace_empty(token, workspace_id):
            exit(1)

        # Step 4: Deploy modules
        print("\n" + "=" * 60)
        print("STEP 4: DEPLOYING MODULES")
        print("=" * 60)
        module_list = [m.strip() for m in MODULES.split(',') if m.strip()]
        all_success = True

        for module in module_list:
            result = deploy_module(token, workspace_id, module)
            if not result:
                all_success = False

        # Final summary
        print("\n" + "=" * 60)
        if all_success:
            print("🎉 DEPLOYMENT COMPLETED SUCCESSFULLY!")
        else:
            print("⚠️  DEPLOYMENT COMPLETED WITH SOME ERRORS")
        print("=" * 60)
        print(f"✅ Client Tenant:  {TARGET_TENANT_ID}")
        print(f"✅ Workspace ID:   {workspace_id}")
        print(f"✅ Modules:        {MODULES}")
        print("=" * 60)

        if not all_success:
            exit(1)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)

if __name__ == "__main__":
    main()
