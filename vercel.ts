/**
 * Vercel configuration for CivicSpark AI frontend deployment.
 * Set VERCEL_BACKEND_URL in Vercel Project Settings → Environment Variables
 */
// Example: https://civicspark-api.onrender.com (no trailing slash)
const backendUrl = process.env.VERCEL_BACKEND_URL || '';

const config = {
  buildCommand: 'cd frontend && npm install && npm run build',
  outputDirectory: 'frontend/dist',
  installCommand: 'cd frontend && npm install',
  framework: null,
  rewrites:
    backendUrl.length > 0
      ? [
          {
            source: '/api/:path*',
            destination: `${backendUrl}/api/:path*`,
          },
        ]
      : [],
};

export default config;
