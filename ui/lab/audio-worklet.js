// Streaming weighted-average downsampling to PCM16 LE, 16 kHz mono.
// Partial frames are discarded on every gate/epoch change, never flushed to the wire.
class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.enabled = false;
    this.epoch = 0;
    this.reset();
    this.port.onmessage = ({ data }) => {
      if (data.type === 'gate') {
        this.enabled = Boolean(data.enabled);
        this.epoch = data.epoch;
        this.reset();
      }
    };
  }
  reset() {
    this.bytes = new ArrayBuffer(3200); // 100 ms; explicitly little endian.
    this.view = new DataView(this.bytes);
    this.index = 0;
    this.weight = 0;
    this.sum = 0;
  }
  process(inputs) {
    const channel = inputs[0]?.[0];
    if (!this.enabled || !channel) return true;
    const ratio = sampleRate / 16000;
    for (const sample of channel) {
      let remaining = 1;
      while (remaining > 1e-8) {
        const amount = Math.min(remaining, ratio - this.weight);
        this.sum += sample * amount;
        this.weight += amount;
        remaining -= amount;
        if (this.weight >= ratio - 1e-8) {
          const value = Math.max(-1, Math.min(1, this.sum / ratio));
          this.view.setInt16(this.index * 2, Math.round(value * (value < 0 ? 32768 : 32767)), true);
          this.index++;
          this.weight = 0;
          this.sum = 0;
          if (this.index === 1600) {
            const buffer = this.bytes;
            this.port.postMessage({ type: 'pcm', buffer, epoch: this.epoch }, [buffer]);
            this.bytes = new ArrayBuffer(3200);
            this.view = new DataView(this.bytes);
            this.index = 0;
          }
        }
      }
    }
    return true;
  }
}
registerProcessor('pcm-capture-processor', PcmCaptureProcessor);
