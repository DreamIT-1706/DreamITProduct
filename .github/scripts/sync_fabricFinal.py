import os
import requests
import time
import json

# Get environment variables
TENANT_ID = os.environ['TENANT_ID']
CLIENT_ID = os.environ['CLIENT_ID']
CLIENT_SECRET = os.environ['CLIENT_SECRET']
CONNECTION_ID = os.environ['CONNECTION_ID']
GITHUB_OWNER = os.environ['GITHUB_OWNER']
REPO_NAME = os.environ['REPO_NAME']
BRANCH_NAME = os.environ['BRANCH_NAME']
WORKSPACE_ID = os.environ.get('WORKSPACE_ID')  # Optional now
WORKSPACE_NAME = os.environ.get('WORKSPACE_NAME')  # New: Name for workspace creation
CAPACITY_ID = os.environ.get('CAPACITY_ID')  # New: Required for workspace creation
ADMIN_USERS = os.environ.get('ADMIN_USERS', '')  # Now supports emails or Object IDs (comma-separated)

BASE_URL = "https://api.fabric.microsoft.com/v1"
GRAPH_URL = "https://graph.microsoft.com/v1.0"

def get_access_token(scope="https://api.fabric.microsoft.com/.default"):
    """Get Azure AD token"""
    print(f"🔐 Getting access token for {scope.split('/')[2]}...")
    token_url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    token_data = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": scope,
        "grant_type": "client_credentials"
    }
    
    response = requests.post(token_url, data=token_data)
    response.raise_for_status()
    token = response.json()["access_token"]
    print("✅ Token acquired successfully")
    return token

def list_workspace_items(token, workspace_id):
    """Get all items in the workspace"""
    print(f"\n📋 Checking workspace items...")
    
    url = f"{BASE_URL}/workspaces/{workspace_id}/items"
    headers = {"Authorization": f"Bearer {token}"}
    
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    
    items = response.json().get("value", [])
    print(f"   Found {len(items)} items in workspace")
    
    return items

def check_workspace_empty(token, workspace_id):
    """Check if workspace is empty, exit if not"""
    print("\n" + "=" * 60)
    print("🔍 PREREQUISITE CHECK: VERIFYING WORKSPACE IS EMPTY")
    print("=" * 60)
    
    items = list_workspace_items(token, workspace_id)
    
    if len(items) > 0:
        print(f"\n❌ ERROR: WORKSPACE IS NOT EMPTY!")
        print(f"\n📦 Workspace contains {len(items)} item(s):")
        for item in items:
            print(f"   - {item['displayName']} ({item['type']})")
        
        print("\n" + "=" * 60)
        print("⚠️  PROCESS CANNOT CONTINUE")
        print("=" * 60)
        print("\n💡 To proceed, you must first:")
        print("   1. Manually delete all items from the workspace, OR")
        print("   2. Use a different empty workspace")
        print("\n🛑 Stopping execution...")
        print("=" * 60)
        return False
    
    print("✅ Workspace is empty - proceeding with sync")
    return True

def list_all_workspaces(token):
    """Get all workspaces accessible by the service principal"""
    url = f"{BASE_URL}/workspaces"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        workspaces = response.json().get("value", [])
        return workspaces
    except Exception as e:
        print(f"⚠️  Error listing workspaces: {e}")
        return []

def find_workspace_by_name(token, workspace_name):
    """Find a workspace by its display name"""
    workspaces = list_all_workspaces(token)
    for ws in workspaces:
        if ws.get("displayName") == workspace_name:
            return ws.get("id")
    return None

def create_workspace(token, workspace_name, capacity_id):
    """Create a new workspace or find existing one with same name"""
    print("\n" + "=" * 60)
    print("🏗️  CREATING NEW WORKSPACE")
    print("=" * 60)
    print(f"   Name: {workspace_name}")
    print(f"   Capacity: {capacity_id}")
    
    # First, check if workspace with this name already exists
    print("\n🔍 Checking if workspace already exists...")
    existing_id = find_workspace_by_name(token, workspace_name)
    
    if existing_id:
        print(f"\n⚠️  Workspace '{workspace_name}' already exists!")
        print(f"   Workspace ID: {existing_id}")
        print(f"\n💡 Using existing workspace instead of creating new one")
        return existing_id
    
    url = f"{BASE_URL}/workspaces"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    body = {
        "displayName": workspace_name,
        "capacityId": capacity_id
    }
    
    try:
        response = requests.post(url, headers=headers, json=body)
        
        if response.status_code == 409:
            # Race condition - workspace was created between our check and now
            print(f"\n⚠️  Workspace was just created by another process")
            print(f"   Searching for workspace ID...")
            existing_id = find_workspace_by_name(token, workspace_name)
            if existing_id:
                print(f"   Found workspace ID: {existing_id}")
                return existing_id
            else:
                print(f"   ❌ Could not find workspace after creation")
                raise Exception("Workspace exists but could not be found")
        
        response.raise_for_status()
        
        workspace_data = response.json()
        workspace_id = workspace_data.get("id")
        
        print(f"\n✅ Workspace created successfully!")
        print(f"   Workspace ID: {workspace_id}")
        print(f"   Display Name: {workspace_data.get('displayName')}")
        
        return workspace_id
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code != 409:  # Already handled 409 above
            print(f"\n❌ Failed to create workspace: {e}")
            print(f"   Response: {e.response.text}")
            raise
    except Exception as e:
        print(f"\n❌ Failed to create workspace: {e}")
        raise

def add_workspace_admin_by_email(token, workspace_id, user_email):
    """Add a user as workspace admin using email address (Power BI API)"""
    url = f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/users"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    body = {
        "emailAddress": user_email,
        "groupUserAccessRight": "Admin"
    }
    
    try:
        response = requests.post(url, headers=headers, json=body)
        
        if response.status_code == 200:
            print(f"  ✅ Added user: {user_email}")
            return True
        elif response.status_code == 409:
            print(f"  ℹ️  User {user_email} already has access")
            return True
        else:
            print(f"  ⚠️  Failed to add {user_email}: {response.status_code}")
            print(f"     Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"  ❌ Error adding {user_email}: {e}")
        return False

def get_existing_workspace_users(token, workspace_id):
    """Get list of existing users in workspace"""
    url = f"https://api.powerbi.com/v1.0/myorg/groups/{workspace_id}/users"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            users = response.json().get('value', [])
            existing_emails = {user.get('emailAddress', '').lower() for user in users if user.get('emailAddress')}
            return existing_emails
        else:
            print(f"  ℹ️  Could not retrieve existing users: {response.status_code}")
            return set()
    except Exception as e:
        print(f"  ℹ️  Could not retrieve existing users: {e}")
        return set()

def add_workspace_admins(token, admin_users_string, workspace_id):
    """Add users as workspace admins using email addresses"""
    print("\n" + "=" * 60)
    print("👥 ADDING WORKSPACE ADMINISTRATORS")
    print("=" * 60)
    
    # Debug: Show what we received
    print(f"\n🔍 Admin users input: '{admin_users_string}'")
    
    if not admin_users_string or not admin_users_string.strip():
        print("⚠️  No admin users to add (ADMIN_USERS environment variable is empty)")
        print("💡 Set ADMIN_USERS='email1@domain.com,email2@domain.com' to add admins")
        return True  # Return True so workflow continues
    
    # Get existing users to avoid duplicates
    print("\n🔍 Checking existing workspace users...")
    existing_emails = get_existing_workspace_users(token, workspace_id)
    if existing_emails:
        print(f"   Found {len(existing_emails)} existing user(s):")
        for email in existing_emails:
            print(f"   - {email}")
    else:
        print(f"   No existing users found")
    
    success_count = 0
    failed_count = 0
    
    # Parse admin users input (comma-separated emails)
    user_emails = [email.strip() for email in admin_users_string.split(',') if email.strip()]
    
    print(f"\n📋 Parsed {len(user_emails)} email(s) to add:")
    for email in user_emails:
        print(f"   - {email}")
    
    if user_emails:
        print(f"\n👤 Adding {len(user_emails)} user(s) as Admin...")
        
        for user_email in user_emails:
            # Validate email format
            if '@' not in user_email:
                print(f"  ⚠️  Invalid email format: {user_email}")
                failed_count += 1
                continue
                
            # Check if user already exists
            email_lower = user_email.lower()
            if email_lower in existing_emails:
                print(f"  ℹ️  User {user_email} already exists in workspace")
                success_count += 1
            else:
                # Add user via Power BI API
                print(f"  🔄 Adding {user_email}...")
                if add_workspace_admin_by_email(token, workspace_id, user_email):
                    success_count += 1
                else:
                    failed_count += 1
            
            time.sleep(0.5)
    
    print(f"\n📊 Admin Assignment Summary:")
    print(f"   ✅ Successfully added: {success_count}")
    print(f"   ❌ Failed: {failed_count}")
    
    if success_count == 0 and failed_count > 0:
        print(f"\n⚠️  WARNING: No admins were added to the workspace!")
        print(f"   The workspace may be inaccessible. Consider adding admins manually.")
        return False
    else:
        print("\n✅ Admin(s) processed successfully!")
        return True

def check_git_connection(token, workspace_id):
    """Check if workspace is connected to Git"""
    url = f"{BASE_URL}/workspaces/{workspace_id}/git/connection"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(url, headers=headers)
        return response.status_code == 200
    except:
        return False

def disconnect_git(token, workspace_id):
    """Disconnect workspace from Git"""
    print(f"\n🔌 Disconnecting workspace from Git...")
    url = f"{BASE_URL}/workspaces/{workspace_id}/git/disconnect"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.post(url, headers=headers)
        if response.status_code == 200:
            print("✅ Workspace disconnected from Git")
            return True
        else:
            print(f"ℹ️  Disconnect response: {response.status_code} (may already be disconnected)")
            return True
    except Exception as e:
        print(f"ℹ️  Disconnect error (may already be disconnected): {e}")
        return True

def connect_workspace_to_git(token, workspace_id):
    """Connect workspace to GitHub"""
    print(f"\n📡 Connecting workspace to Git...")
    url = f"{BASE_URL}/workspaces/{workspace_id}/git/connect"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    body = {
        "gitProviderDetails": {
            "gitProviderType": "GitHub",
            "ownerName": GITHUB_OWNER,
            "repositoryName": REPO_NAME,
            "branchName": BRANCH_NAME,
            "directoryName": ""
        },
        "myGitCredentials": {
            "source": "ConfiguredConnection",
            "connectionId": CONNECTION_ID
        }
    }
    
    response = requests.post(url, headers=headers, json=body)
    
    if response.status_code in [200, 409]:
        print("✅ Workspace connected to Git")
        return True
    else:
        print(f"❌ Connection failed: {response.status_code}")
        print(f"   Response: {response.text}")
        raise Exception(f"Failed to connect: {response.text}")

def get_git_status(token, workspace_id):
    """Get Git status to check sync state"""
    print("\n🔍 Checking Git status...")
    url = f"{BASE_URL}/workspaces/{workspace_id}/git/status"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Git status retrieved")
            print(f"   Workspace Head: {data.get('workspaceHead') or 'None'}")
            print(f"   Remote Commit: {data.get('remoteCommitHash')}")
            return data
        else:
            print(f"⚠️  Git status not available: {response.status_code}")
            return None
    except Exception as e:
        print(f"⚠️  Error getting git status: {e}")
        return None

def initialize_connection(token, workspace_id):
    """Initialize Git connection"""
    print("\n🔄 Initializing Git connection...")
    url = f"{BASE_URL}/workspaces/{workspace_id}/git/initializeConnection"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    body = {"initializationStrategy": "PreferRemote"}
    
    response = requests.post(url, headers=headers, json=body)
    
    if response.status_code != 200:
        print(f"⚠️  Initialize response: {response.status_code}")
        print(f"   Response: {response.text}")
    
    response.raise_for_status()
    
    data = response.json()
    print(f"✅ Connection initialized")
    print(f"   Required Action: {data.get('requiredAction')}")
    print(f"   Workspace Head: {data.get('workspaceHead') or 'None'}")
    print(f"   Remote Commit: {data.get('remoteCommitHash')}")
    
    return data

def update_from_git_with_retry(token, workspace_id, workspace_head, remote_commit, max_retries=3):
    """Pull items from Git to workspace with retry logic"""
    
    for attempt in range(max_retries):
        print(f"\n⬇️  Syncing items from Git (Attempt {attempt + 1}/{max_retries})...")
        
        url = f"{BASE_URL}/workspaces/{workspace_id}/git/updateFromGit"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # Build request body
        body = {
            "remoteCommitHash": remote_commit,
            "conflictResolution": {
                "conflictResolutionType": "Workspace",
                "conflictResolutionPolicy": "PreferRemote"
            },
            "options": {
                "allowOverrideItems": True
            }
        }
        
        # Only include workspaceHead if it's not None
        if workspace_head:
            body["workspaceHead"] = workspace_head
        
        print(f"📤 Request details:")
        print(f"   Remote commit: {remote_commit[:12]}...")
        print(f"   Workspace head: {workspace_head or 'None (empty workspace)'}")
        
        try:
            response = requests.post(url, headers=headers, json=body)
            
            if response.status_code == 202:
                operation_id = response.headers.get("x-ms-operation-id")
                print(f"✅ Sync initiated (Operation: {operation_id})")
                return operation_id
            else:
                print(f"⚠️  Response status: {response.status_code}")
                print(f"📥 Response body: {response.text}")
                
                # Check if it's a retriable error
                error_data = response.json() if response.text else {}
                error_code = error_data.get('errorCode', '')
                
                if error_code == 'UnknownError' and attempt < max_retries - 1:
                    print(f"⏳ Retrying in 10 seconds...")
                    time.sleep(10)
                    continue
                else:
                    response.raise_for_status()
                    
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"❌ Error: {e}")
                print(f"⏳ Retrying in 10 seconds...")
                time.sleep(10)
            else:
                raise
    
    raise Exception("Failed to sync after all retries")

def poll_operation(token, operation_id):
    """Wait for operation to complete"""
    print("\n⏳ Waiting for operation to complete...")
    
    url = f"{BASE_URL}/operations/{operation_id}"
    headers = {"Authorization": f"Bearer {token}"}
    
    for attempt in range(60):
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            
            status_data = response.json()
            status = status_data.get("status")
            percent = status_data.get("percentComplete", 0)
            
            if percent:
                print(f"   Status: {status} - {percent}% (Attempt {attempt + 1}/60)")
            else:
                print(f"   Status: {status} (Attempt {attempt + 1}/60)")
            
            if status == "Succeeded":
                print("✅ Operation completed successfully!")
                return True
            elif status == "Failed":
                error = status_data.get("error", {})
                print(f"❌ Operation failed!")
                print(f"   Error Code: {error.get('code', 'Unknown')}")
                print(f"   Error Message: {error.get('message', 'Unknown')}")
                return False
            
        except Exception as e:
            print(f"⚠️  Error polling (attempt {attempt + 1}): {e}")
        
        time.sleep(5)
    
    print("❌ Operation timed out")
    return False

def main():
    print("=" * 60)
    print("🚀 Fabric Workspace Git Sync Workflow")
    print("=" * 60)
    print(f"📦 Repository: {GITHUB_OWNER}/{REPO_NAME}")
    print(f"🌿 Branch: {BRANCH_NAME}")
    
    # Determine workspace strategy
    if WORKSPACE_ID:
        print(f"🏢 Using existing workspace: {WORKSPACE_ID}")
        workspace_id = WORKSPACE_ID
        create_new = False
    elif WORKSPACE_NAME and CAPACITY_ID:
        print(f"🏗️  Will create new workspace: {WORKSPACE_NAME}")
        create_new = True
    else:
        print("\n❌ ERROR: Configuration missing!")
        print("   You must provide either:")
        print("   - WORKSPACE_ID (to use existing workspace), OR")
        print("   - WORKSPACE_NAME + CAPACITY_ID (to create new workspace)")
        exit(1)
    
    print("=" * 60)
    
    try:
        # Step 1: Authenticate
        token = get_access_token()
        
        # Step 2: Create workspace if needed
        if create_new:
            workspace_id = create_workspace(token, WORKSPACE_NAME, CAPACITY_ID)
            print(f"\n⏳ Waiting 5 seconds for workspace to initialize...")
            time.sleep(5)
            
            # Add admins to the newly created workspace (now supports emails directly!)
            add_workspace_admins(token, ADMIN_USERS, workspace_id)
            print(f"\n⏳ Waiting 3 seconds after adding admins...")
            time.sleep(3)
        
        # Step 3: CHECK IF WORKSPACE IS EMPTY (REQUIRED)
        if not check_workspace_empty(token, workspace_id):
            exit(1)
        
        # Step 4: Disconnect if already connected
        if check_git_connection(token, workspace_id):
            disconnect_git(token, workspace_id)
            time.sleep(5)
        
        # Step 5: Connect to Git
        print("\n" + "=" * 60)
        print("STEP 1: CONNECTING TO GIT")
        print("=" * 60)
        
        connect_workspace_to_git(token, workspace_id)
        
        print("\n⏳ Waiting 10 seconds for connection to stabilize...")
        time.sleep(10)
        
        # Step 6: Check Git status first
        git_status = get_git_status(token, workspace_id)
        
        if git_status:
            workspace_head = git_status.get("workspaceHead")
            remote_commit = git_status.get("remoteCommitHash")
        else:
            # Fallback to initialize if status not available
            init_data = initialize_connection(token, workspace_id)
            workspace_head = init_data.get("workspaceHead")
            remote_commit = init_data.get("remoteCommitHash")
            required_action = init_data.get("requiredAction")
            
            if required_action != "UpdateFromGit":
                print(f"\n⚠️  Unexpected required action: {required_action}")
                if required_action == "None":
                    print("✅ No sync needed")
                    return
        
        # Step 7: Sync from Git with retries
        print("\n" + "=" * 60)
        print("STEP 2: SYNCING FROM GIT")
        print("=" * 60)
        
        print(f"\n📊 Syncing items from Git:")
        print(f"   Commit: {remote_commit[:12]}...")
        
        operation_id = update_from_git_with_retry(token, workspace_id, workspace_head, remote_commit)
        
        if not poll_operation(token, operation_id):
            print("\n❌ Sync operation failed")
            exit(1)
        
        # Step 8: Disconnect from Git
        print("\n" + "=" * 60)
        print("STEP 3: DISCONNECTING FROM GIT")
        print("=" * 60)
        
        time.sleep(3)
        disconnect_git(token, workspace_id)
        
        # Verify disconnection
        time.sleep(3)
        if check_git_connection(token, workspace_id):
            print("⚠️  Warning: Workspace may still be connected")
        else:
            print("✅ Confirmed: Workspace is disconnected from Git")
        
        # Final summary
        print("\n" + "=" * 60)
        print("🎉 WORKFLOW COMPLETED SUCCESSFULLY!")
        print("=" * 60)
        if create_new:
            print("✅ Step 0: New workspace created")
            print("✅ Step 0.1: Admins added to workspace")
        print("✅ Step 1: Connected to Git")
        print("✅ Step 2: Items synced from Git")
        print("✅ Step 3: Disconnected from Git")
        print("\n📋 WORKSPACE STATUS:")
        print(f"   - Workspace ID: {workspace_id}")
        print(f"   - Contains items from commit: {remote_commit[:12]}...")
        print("   - Standalone (not connected to Git)")
        print("   - Changes will NOT be committed")
        if create_new and ADMIN_USERS:
            user_count = len([u for u in ADMIN_USERS.split(',') if u.strip()])
            print(f"   - Admins: Service Principal + {user_count} user(s)")
        elif create_new:
            print(f"   - Admins: Service Principal only")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error occurred: {e}")
        import traceback
        print("\n📋 Full traceback:")
        traceback.print_exc()
        print("=" * 60)
        exit(1)

if __name__ == "__main__":
    main()
