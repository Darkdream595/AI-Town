import { EventBus } from '../core/EventBus';

export interface QaRuntimeMetadataInput {
  fixture_id: string;
  entity_count: number;
  scene_id: string;
  revision: number;
  camera: {
    x_wu: number;
    y_wu: number;
    zoom: number;
  };
}

export interface QaRuntimeMetadata extends QaRuntimeMetadataInput {
  schema_version: 'qa.runtime.v1';
}

export function createQaRuntimeMetadata(
  input: QaRuntimeMetadataInput,
): QaRuntimeMetadata {
  return { schema_version: 'qa.runtime.v1', ...input };
}

export class RafFrameSampler {
  private frameRequestId: number | null = null;
  private lastTimestamp: number | null = null;
  private readonly frameSamples: number[] = [];

  constructor(
    private readonly requestFrame: (callback: FrameRequestCallback) => number,
    private readonly cancelFrame: (requestId: number) => void,
  ) {}

  start(): void {
    if (this.frameRequestId === null) {
      this.frameRequestId = this.requestFrame(this.handleFrame);
    }
  }

  stop(): void {
    if (this.frameRequestId !== null) {
      this.cancelFrame(this.frameRequestId);
      this.frameRequestId = null;
    }
    this.lastTimestamp = null;
  }

  samples(): number[] {
    return [...this.frameSamples];
  }

  private readonly handleFrame = (timestamp: number): void => {
    if (this.lastTimestamp !== null) {
      this.frameSamples.push(timestamp - this.lastTimestamp);
    }
    this.lastTimestamp = timestamp;
    this.frameRequestId = this.requestFrame(this.handleFrame);
  };
}

interface QaRuntimeTarget {
  requestAnimationFrame(callback: FrameRequestCallback): number;
  cancelAnimationFrame(requestId: number): void;
  __AI_TOWN_QA_RUNTIME__?: {
    metadata: QaRuntimeMetadata | null;
    frame_samples_ms: () => number[];
    capabilities: Record<string, boolean>;
    event_log: readonly unknown[];
    event_log_sha256: string;
  };
}

interface RuntimeMetadataEvent extends QaRuntimeMetadataInput {
  capabilities: Record<string, boolean>;
  event_log: readonly unknown[];
  event_log_sha256: string;
}

export function installQaRuntimeExposure(
  target: QaRuntimeTarget,
  fixtureId: string | null,
): () => void {
  if (fixtureId === null) {
    return () => undefined;
  }

  const sampler = new RafFrameSampler(
    callback => target.requestAnimationFrame(callback),
    requestId => target.cancelAnimationFrame(requestId),
  );
  target.__AI_TOWN_QA_RUNTIME__ = {
    metadata: null,
    frame_samples_ms: () => sampler.samples(),
    capabilities: {},
    event_log: [],
    event_log_sha256: '',
  };

  const handleMetadata = (event: RuntimeMetadataEvent): void => {
    const runtime = target.__AI_TOWN_QA_RUNTIME__;
    if (!runtime || event.fixture_id !== fixtureId) {
      return;
    }
    runtime.metadata = createQaRuntimeMetadata(event);
    runtime.capabilities = { ...event.capabilities };
    runtime.event_log = [...event.event_log];
    runtime.event_log_sha256 = event.event_log_sha256;
  };

  EventBus.on('qa:runtime-metadata', handleMetadata);
  sampler.start();
  return () => {
    EventBus.off('qa:runtime-metadata', handleMetadata);
    sampler.stop();
  };
}
