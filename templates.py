def render_spotify_setup_page(client_id: str, client_secret_status: str, lan_ip: str) -> str:
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>Spotify Setup</title>

        <!-- Tailwind CSS -->
        <script src="https://cdn.tailwindcss.com"></script>

        <!-- Google Fonts -->
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&family=JetBrains+Mono&display=swap" rel="stylesheet">

        <style>
            body {{
                font-family: 'Inter', sans-serif;
            }}
            code {{
                font-family: 'JetBrains Mono', monospace;
            }}
        </style>
    </head>
    <body class="bg-gray-100 text-gray-800 min-h-screen flex items-center justify-center p-6">
        <div class="bg-white rounded-2xl shadow-xl max-w-xl w-full p-6 space-y-6">
            <h2 class="text-2xl font-extrabold text-green-600">Spotify Setup</h2>

            <p>To use Spotify features, you must authenticate with Spotify:</p>

            <form action="/auth/spotify" method="get">
                <button
                    type="submit"
                    class="bg-green-500 hover:bg-green-600 text-white font-semibold px-4 py-2 rounded-lg transition duration-200 shadow-md"
                >
                    Authenticate with Spotify
                </button>
            </form>

            <div class="border-t pt-4 space-y-2 text-sm">
                <p><strong>Client ID:</strong> <code>{client_id}</code></p>
                <p><strong>Client Secret:</strong>
                    <span class="text-{'green' if client_secret_status == 'SET' else 'red'}-600">
                        {client_secret_status}
                    </span>
                </p>
                <p><strong>Detected LAN IP:</strong> <code>{lan_ip}</code></p>
            </div>

            <!-- Static Attention Box -->
            <div class="bg-yellow-100 border border-yellow-300 p-4 rounded-lg text-yellow-900 shadow-md text-sm">
                <h3 class="font-semibold text-md mb-1">⚠️ Important Note</h3>
                <p>If you're accessing this page from another device on your network (like your phone), the redirect will fail because it's set to <code>127.0.0.1</code></p>
                <p class="mt-2">Instead, manually edit the browser's URL after login to:</p>
                <code class="block bg-yellow-200 text-gray-800 p-2 rounded-md mt-1 overflow-scroll">
                    http://{lan_ip}:8000/auth/spotify/callback
                </code>
            </div>
        </div>
    </body>
    </html>
    """
