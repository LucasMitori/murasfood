/**
 * A liveness probe that costs nothing.
 *
 * The container's healthcheck runs for the life of the process, and pointing it
 * at `/` meant a full server-side render every interval. In dev each render
 * pulls modules through Vite's transform pipeline and leaves ~30 MB behind, so
 * the probe meant to prove the server was healthy was steadily making it less
 * so — until the Nitro worker hit Node's heap limit and every route answered
 * "Worker terminated due to reaching memory limit".
 *
 * This renders nothing. The startup warm-up still exercises the real pages;
 * this only answers "is the process still up".
 */
export default defineEventHandler(() => ({
  status: 'ok',
  uptime: Math.round(process.uptime()),
}))
