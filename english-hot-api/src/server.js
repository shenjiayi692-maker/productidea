import { serve } from "@hono/node-server";
import { app } from "./app.js";

const port = Number(process.env.PORT || 6689);
serve({ fetch: app.fetch, port });
console.log(`english-hot-api running at http://localhost:${port}`);
