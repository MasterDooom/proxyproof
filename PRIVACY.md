# ProxyProof Privacy Notice (Internal Testing)

Last updated: 2026-10-13

ProxyProof is an internal-test attendance prototype. Do not use it for high-stakes attendance decisions or deploy it for a real student population until hosting, access control, data retention, incident handling, and security review are complete.

## Data processed

When you use ProxyProof, the service may store:

- Username, display name, account role, and a password hash. Plaintext passwords are not stored by the API.
- An app-installation UUID used to bind a student account to one installation. It is not a hardware identifier or hardware-backed attestation.
- Room definitions, room-enrolment records, organiser ownership, and scheduled class/session information.
- Attendance status, timestamp, whether it was marked by BLE or manual correction, and the observed BLE RSSI value for successful BLE attendance.
- API tokens are returned at sign-in, hashed in the server database, and valid for a limited period. The Android client encrypts the saved token with an Android Keystore-backed key.
- The hosting platform may process connection metadata, including source IP addresses, timestamps, and service request logs.

The app does not intentionally collect or persist GPS coordinates. On older Android versions, the operating system may require location permission for BLE scanning; ProxyProof requests that permission for the platform's BLE requirement, not to track a route or record location.

## Purposes and access

Data is used to authenticate accounts, organise rooms and sessions, validate attendance attempts, show students their own history, and allow organisers to inspect or export records for sessions they own. The deployment operator and authorised database administrators can access stored records as required to operate and troubleshoot the service. Hosting providers process data to provide the infrastructure.

The prototype does not include advertising or analytics SDKs. Do not infer that this prototype has completed an independent privacy audit.

## Retention and deletion

There is currently no self-service account or attendance-record deletion workflow and no automatic retention/deletion schedule. The current hosted internal-test deployment uses SQLite on Render's temporary filesystem, so accounts and attendance may be lost when the service restarts or redeploys. Do not use it for official records. After replacing DATABASE_URL with the private PostgreSQL Internal Database URL, records remain until an authorised database operator deletes them. Before using ProxyProof with real students, the deployment owner must publish a contact channel, define a retention period, implement and test deletion/export procedures, and explain those procedures to users.

A free Render Postgres instance expires 30 days after creation unless upgraded; that hosting limitation is not a retention strategy or a backup plan. Use an appropriate durable database plan and tested backup/restore procedure before any real deployment.

## Bluetooth and presence limitations

The app uses short-lived rotating BLE tokens and a dwell/RSSI heuristic. RSSI varies with phone hardware, bodies, doors, walls and interference; it cannot prove that a person is physically inside a room. A rotating token does not prevent every live relay or capable spoofing attack. The current manufacturer identifier 0xFFFF is development-only and must be replaced with an appropriate protocol identifier before public distribution.

The initial implementation is foreground-only. Keep the relevant app screen open, Bluetooth enabled, and nearby-device permissions granted. Background attendance is not promised.

## Security status

The prototype hashes passwords, stores server-side bearer-token digests, encrypts a locally saved Android token, validates organiser permissions, and enforces the server-side automatic-attendance deadline. These measures do not amount to a full production security assessment. In particular, shared/distributed rate limiting, account recovery, organiser-approved device replacement, stronger device attestation, production BLE identifier assignment, incident response, and formal retention/deletion controls remain release work.

## Questions and data requests

Contact the person or organisation that administers the specific ProxyProof deployment. Each deployment owner must provide a real contact channel before inviting real users. The project currently does not implement a self-service mechanism for deleting an account or its associated attendance data.
