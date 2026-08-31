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

  async connect(url, token) {
    log("info", "loading livekit-client module");
    this.client = await import(LIVEKIT_BROWSER_MODULE);
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

  async publishMicrophone() {
    log("info", "requesting microphone (getUserMedia audio)");
    const track = await this.client.createLocalAudioTrack({
      echoCancellation: true,
      noiseSuppression: true,
    });
    await this.room.localParticipant.publishTrack(track);
    this.localTracks.push(track);
    log("info", "microphone track published", { sid: track?.sid, label: track?.mediaStreamTrack?.label });
    return track;
  }

  async publishCamera() {
    log("info", "requesting camera (getUserMedia video)");
    const track = await this.client.createLocalVideoTrack({
      resolution: { width: 1280, height: 720 },
    });
    await this.room.localParticipant.publishTrack(track);
    this.localTracks.push(track);
    log("info", "camera track published", { sid: track?.sid, label: track?.mediaStreamTrack?.label });
    return track;
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
