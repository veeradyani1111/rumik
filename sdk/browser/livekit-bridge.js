const LIVEKIT_BROWSER_MODULE = "https://cdn.jsdelivr.net/npm/livekit-client@2.22.1/+esm";


function log(level, message, detail) {
  const fn = console[level] ?? console.info;
  fn.call(console, `[rumik-bridge] ${message}`, detail ?? "");
}


export class LiveKitBridge {
  constructor({ onState = () => {}, onData = () => {}, onAudioTrack = () => {} } = {}) {
    this.onState = onState;
    this.onData = onData;
    this.onAudioTrack = onAudioTrack;
    this.room = null;
    this.client = null;
    this.localTracks = [];
  }

  async load() {
    if (this.client) return this.client;
    log("info", "loading livekit-client module");
    this.client = await import(LIVEKIT_BROWSER_MODULE);
    return this.client;
  }

  // Media is ACQUIRED (permission prompts, device opened) before the room is
  // joined and PUBLISHED after: the agent greets the moment a participant
  // appears in the room, so joining first meant the greeting played while the
  // browser's camera prompt was still open.
  async acquireMicrophone() {
    await this.load();
    log("info", "requesting microphone (getUserMedia audio)");
    const track = await this.client.createLocalAudioTrack({
      echoCancellation: true,
      noiseSuppression: true,
    });
    this.localTracks.push(track);
    log("info", "microphone ready", { label: track?.mediaStreamTrack?.label });
    return track;
  }

  async acquireCamera() {
    await this.load();
    log("info", "requesting camera (getUserMedia video)");
    // 1080p: card stills are grabbed straight off this local track, so its
    // native resolution — not the WebRTC-compressed stream — sets read quality.
    const track = await this.client.createLocalVideoTrack({
      resolution: { width: 1920, height: 1080 },
    });
    this.localTracks.push(track);
    log("info", "camera ready", { label: track?.mediaStreamTrack?.label });
    return track;
  }

  async publishTrack(track) {
    await this.room.localParticipant.publishTrack(track);
    log("info", "track published", { sid: track?.sid, kind: track?.kind });
    return track;
  }

  async connect(url, token) {
    await this.load();
    const { Room, RoomEvent, Track } = this.client;
    this.room = new Room({ adaptiveStream: true, dynacast: true });

    this.room
      .on(RoomEvent.Reconnecting, () => {
        log("warn", "reconnecting to room");
        this.onState("reconnecting");
      })
      .on(RoomEvent.Reconnected, () => {
        log("info", "reconnected to room");
        this.onState("live");
      })
      .on(RoomEvent.Disconnected, (reason) => {
        log("warn", "disconnected from room", { reason });
        this.onState("ended");
      })
      .on(RoomEvent.ParticipantConnected, (participant) => {
        log("info", "participant connected", { identity: participant?.identity });
      })
      .on(RoomEvent.ParticipantDisconnected, (participant) => {
        log("info", "participant disconnected", { identity: participant?.identity });
      })
      .on(RoomEvent.TrackPublished, (pub, participant) => {
        log("info", "remote track published", {
          identity: participant?.identity,
          kind: pub?.kind,
        });
      })
      .on(RoomEvent.DataReceived, (bytes, participant) => {
        let payload;
        try {
          payload = JSON.parse(new TextDecoder().decode(bytes));
        } catch {
          // Application data that does not belong to this SDK — ignore quietly.
          return;
        }
        log("info", "data received", { from: participant?.identity, type: payload?.type });
        this.onData(payload);
      })
      .on(RoomEvent.TrackSubscribed, (track, _pub, participant) => {
        log("info", "subscribed to remote track", {
          identity: participant?.identity,
          kind: track?.kind,
        });
        if (track.kind === Track.Kind.Audio) this.onAudioTrack(track);
      });

    log("info", "connecting to livekit", { url });
    await this.room.connect(url, token);
    log("info", "connected to livekit room", {
      room: this.room?.name,
      localIdentity: this.room?.localParticipant?.identity,
    });
  }

  async sendData(payload) {
    const bytes = new TextEncoder().encode(JSON.stringify(payload));
    await this.room.localParticipant.publishData(bytes, { reliable: true });
    log("info", "data sent", { type: payload?.type });
  }

  async disconnect() {
    log("info", "disconnecting", { tracks: this.localTracks.length });
    for (const track of this.localTracks) track.stop();
    this.localTracks = [];
    await this.room?.disconnect();
  }
}
