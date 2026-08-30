import { LiveKitBridge } from "./livekit-bridge.js";


const noop = () => {};


export function buildSessionPayload(config) {
  const tools = Object.entries(config.tools ?? {}).map(([name, tool]) => ({
    name,
    description: tool.description,
    parameters: tool.parameters ?? {},
  }));
  return {
    prompt: config.prompt,
    vision: config.vision ?? false,
    ...(config.voice ? { voice: config.voice } : {}),
    tools,
    options: config.options ?? {},
  };
}


export async function runToolHandler(tools, call) {
  const handler = tools?.[call.name]?.handler;
  if (typeof handler !== "function") {
    return { type: "tool_result", id: call.id, result: { error: "unknown_tool" } };
  }
  try {
    const result = await handler(call.args ?? {});
    return { type: "tool_result", id: call.id, result };
  } catch (error) {
    return {
      type: "tool_result",
      id: call.id,
      result: { error: error instanceof Error ? error.message : String(error) },
    };
  }
}


class AgentController {
  constructor(config, dependencies = {}) {
    if (!config?.session) throw new TypeError("session URL is required");
    if (!config?.prompt?.trim()) throw new TypeError("prompt is required");
    this.config = config;
    const fetchImpl = dependencies.fetch ?? globalThis.fetch;
    this.fetch = (...args) => fetchImpl.call(globalThis, ...args);
    this.document = dependencies.document ?? globalThis.document;
    this.Bridge = dependencies.Bridge ?? LiveKitBridge;
    this.bridge = null;
    this.elements = {};
    this.stopped = false;
  }

  async mount(target) {
    const root = typeof target === "string" ? this.document.querySelector(target) : target;
    if (!root) throw new TypeError("mount target was not found");
    this._render(root);
    this._state("connecting");

    try {
      const response = await this.fetch(this.config.session, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(buildSessionPayload(this.config)),
      });
      const session = await response.json();
      if (!response.ok) throw Object.assign(new Error(session.message ?? "Session failed"), session);
      this.config.onEvent?.({ type: "session_started", room: session.room });

      this.bridge = new this.Bridge({
        onState: (state) => this._state(state),
        onData: (payload) => this._onData(payload),
        onAudioTrack: (track) => track.attach(this.elements.audio),
      });
      await this.bridge.connect(session.url, session.token);
      try {
        await this.bridge.publishMicrophone();
      } catch (cause) {
        const error = Object.assign(new Error("Microphone permission is required"), {
          code: "mic_required",
          cause,
        });
        this._error(error);
        await this.stop();
        throw error;
      }
      if (this.config.vision) {
        try {
          const camera = await this.bridge.publishCamera();
          camera.attach(this.elements.video);
        } catch {
          this.config.onEvent?.({ type: "camera_unavailable" });
        }
      }
      this._state("live");
      return this;
    } catch (error) {
      if (error.code !== "mic_required") this._error(error);
      throw error;
    }
  }

  async stop() {
    if (this.stopped) return;
    this.stopped = true;
    await this.bridge?.disconnect();
    this._state("ended");
  }

  async _onData(payload) {
    this.config.onEvent?.(payload);
    if (payload?.type !== "tool_call") return;
    const result = await runToolHandler(this.config.tools ?? {}, payload);
    await this.bridge.sendData(result);
  }

  _render(root) {
    const shell = this.document.createElement("section");
    shell.className = "rumik-agent";
    const video = this.document.createElement("video");
    video.className = "rumik-agent__preview";
    video.autoplay = true;
    video.muted = true;
    video.playsInline = true;
    video.hidden = !this.config.vision;
    const audio = this.document.createElement("audio");
    audio.autoplay = true;
    const status = this.document.createElement("p");
    status.className = "rumik-agent__status";
    shell.append(video, audio, status);
    root.replaceChildren(shell);
    this.elements = { shell, video, audio, status };
  }

  _state(state) {
    if (this.elements.status) this.elements.status.textContent = state;
    (this.config.onState ?? noop)(state);
  }

  _error(error) {
    (this.config.onError ?? noop)(error);
    this._state("error");
  }
}


export const RumikAgent = {
  create(config, dependencies) {
    return new AgentController(config, dependencies);
  },
};
