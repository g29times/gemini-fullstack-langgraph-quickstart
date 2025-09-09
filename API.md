#!/bin/bash
set -e -E

GEMINI_API_KEY=""
MODEL_ID="gemini-2.5-flash-image-preview"
GENERATE_CONTENT_API="streamGenerateContent"

cat << EOF > request.json
{
    "contents": [
      {
        "role": "user",
        "parts": [
          {
            "text": "Hi"
          },
        ]
      },
    ],
    "generationConfig": {
      "responseModalities": ["IMAGE", "TEXT", ],
    },
}
EOF

curl \
-X POST \
-H "Content-Type: application/json" \
"https://generativelanguage.googleapis.com/v1beta/models/${MODEL_ID}:${GENERATE_CONTENT_API}?key=${GEMINI_API_KEY}" -d '@request.json'
