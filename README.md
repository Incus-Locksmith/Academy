# Locksmith Call Handler Academy Quiz — MVP

This first version includes:

- Student name and email capture
- Three training modules
- Fifteen multiple-choice questions
- Immediate marking and explanations
- An 80% pass mark
- Retakes
- Saved attempts in PostgreSQL
- Password-protected manager results dashboard
- Render Blueprint configuration
- Health-check route

## Deploy on Render

1. Create a new GitHub repository.
2. Upload every file in this folder to the repository root.
3. In Render, choose **New > Blueprint**.
4. Connect the GitHub repository.
5. Render will read `render.yaml` and propose:
   - one Flask web service;
   - one PostgreSQL database.
6. During setup, enter a strong value for `ADMIN_PASSWORD`.
7. Approve the Blueprint and deploy.
8. Open the generated Render web-service URL.
9. Student area: `/`
10. Manager area: `/admin`

## Important storage note

Student results are stored in Render PostgreSQL, not in the web service's local filesystem.

Render's free PostgreSQL databases currently expire after 30 days. Use a paid
PostgreSQL plan before this becomes a live long-term training record.

## Local testing

Create a virtual environment, then run:

    pip install -r requirements.txt
    python app.py

The local version uses SQLite automatically.

Default local manager password:

    ChangeMe123!

Set a proper password before public use:

Windows PowerShell:

    $env:ADMIN_PASSWORD="your-strong-password"
    python app.py

macOS/Linux:

    export ADMIN_PASSWORD="your-strong-password"
    python app.py

## Next build stages

- Full Academy question bank
- Student accounts and saved progress
- Final assessment
- Readiness status
- Trainer sign-off
- Per-question weakness reporting
- CSV/Excel result export
- Certificates
