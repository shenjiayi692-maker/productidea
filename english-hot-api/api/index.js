// Vercel 入口（Serverless Function）
import { handle } from "hono/vercel";
import { app } from "../src/app.js";

export default handle(app);
