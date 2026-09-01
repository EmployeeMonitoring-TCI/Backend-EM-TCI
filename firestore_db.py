import firebase_admin
from firebase_admin import firestore


def get_db():
    app = firebase_admin.get_app()
    client = firestore.client(app=app)

    # Firestore currently rejects the encoded parentheses in the default database ID.
    client._database_string_internal = (
        f"projects/{app.project_id}/databases/(default)"
    )
    return client