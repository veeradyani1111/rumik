import {
  Room,
  RoomEvent,
  Track,
  createLocalAudioTrack,
  createLocalVideoTrack,
} from "livekit-client";


export class LiveKitBridge {
  constructor({ onState = () => {}, onData = () => {}, onAudioTrack = () => {} } = {}) {
    this.onState = onState;
    this.onData = onData;
    this.onAudioTrack = onAudioTrack;
    this.room = new Room({ adaptiveStream: true, dynacast: true });
    this.localTracks = [];

    this.room.on(RoomEvent.Reconnecting, () => this.onState("reconnecting"));
    this.room.on(RoomEvent.Reconnected, () => this.onState("live"));
    this.room.on(RoomEvent.Disconnected, () => this.onState("ended"));
    this.room.on(RoomEvent.DataReceived, (bytes) => {
      try {
        this.onData(JSON.parse(new TextDecoder().decode(bytes)));
      } catch {
        // Ignore application data that does not belong to this SDK.
      }
    });
    this.room.on(RoomEvent.TrackSubscribed, (track) => {
      if (track.kind === Track.Kind.Audio) this.onAudioTrack(track);
    });
  }

  async connect(url, token) {
    await this.room.connect(url, token);
  }

  async publishMicrophone() {
    const track = await createLocalAudioTrack({ echoCancellation: true, noiseSuppression: true });
    await this.room.localParticipant.publishTrack(track);
    this.localTracks.push(track);
    return track;
  }

  async publishCamera() {
    const track = await createLocalVideoTrack({ resolution: { width: 1280, height: 720 } });
    await this.room.localParticipant.publishTrack(track);
    this.localTracks.push(track);
    return track;
  }

  async sendData(payload) {
    const bytes = new TextEncoder().encode(JSON.stringify(payload));
    await this.room.localParticipant.publishData(bytes, { reliable: true });
  }

  async disconnect() {
    for (const track of this.localTracks) track.stop();
    this.localTracks = [];
    await this.room.disconnect();
  }
}

