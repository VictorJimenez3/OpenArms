/**
 * OpenArms Lab - AudioWorklet Microphone Capture Processor
 *
 * Runs in the Web Audio rendering thread.
 * Captures microphone audio, resamples from device sample rate to 16,000 Hz,
 * quantizes Float32 [-1.0, 1.0] to 16-bit signed PCM (Int16Array),
 * and buffers into chunks (~100ms = 1600 samples) posted to the main thread
 * for base64 encoding and transmission over the Gemini Live WebSocket.
 */

class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.targetSampleRate = 16000;
    this.bufferSize = 1600; // 100ms chunk at 16kHz
    this.outputBuffer = new Int16Array(this.bufferSize);
    this.outputIndex = 0;

    // Resampling state
    this.sourceIndex = 0;
    this.lastInputSample = 0;
    this.isMuted = false;

    // Handle messages from main thread
    this.port.onmessage = (event) => {
      const data = event.data;
      if (!data) return;
      if (data.type === 'mute') {
        this.isMuted = !!data.muted;
      } else if (data.type === 'flush') {
        this.flush();
      }
    };
  }

  flush() {
    if (this.outputIndex > 0) {
      const chunk = this.outputBuffer.slice(0, this.outputIndex);
      this.port.postMessage(
        {
          type: 'pcm',
          buffer: chunk.buffer,
          sampleCount: this.outputIndex,
        },
        [chunk.buffer]
      );
      this.outputIndex = 0;
    }
  }

  process(inputs, outputs, parameters) {
    if (this.isMuted) {
      // Discard input when muted
      return true;
    }

    const input = inputs[0];
    if (!input || input.length === 0) {
      return true;
    }

    const channel = input[0];
    if (!channel || channel.length === 0) {
      return true;
    }

    const inLength = channel.length;
    const ratio = sampleRate / this.targetSampleRate;

    // Linear interpolation resampling from hardware sampleRate down to 16000 Hz
    while (this.sourceIndex < inLength) {
      const indexFloor = Math.floor(this.sourceIndex);
      const fraction = this.sourceIndex - indexFloor;

      const s0 = indexFloor === 0 && this.sourceIndex < 1
        ? (fraction === 0 ? channel[0] : (this.lastInputSample * (1 - fraction) + channel[0] * fraction))
        : (indexFloor < inLength - 1
            ? channel[indexFloor] * (1 - fraction) + channel[indexFloor + 1] * fraction
            : channel[inLength - 1]);

      // Clamp to [-1.0, 1.0]
      const clamped = Math.max(-1.0, Math.min(1.0, s0));

      // Quantize to 16-bit signed integer [-32768, 32767]
      const pcm16 = clamped < 0 ? Math.round(clamped * 32768) : Math.round(clamped * 32767);

      this.outputBuffer[this.outputIndex++] = Math.max(-32768, Math.min(32767, pcm16));

      if (this.outputIndex >= this.bufferSize) {
        // Send chunk to main thread
        const chunk = this.outputBuffer.slice(0, this.bufferSize);
        this.port.postMessage(
          {
            type: 'pcm',
            buffer: chunk.buffer,
            sampleCount: this.bufferSize,
          },
          [chunk.buffer]
        );
        this.outputIndex = 0;
      }

      this.sourceIndex += ratio;
    }

    this.sourceIndex -= inLength;
    this.lastInputSample = channel[inLength - 1];

    return true;
  }
}

registerProcessor('pcm-capture-processor', PcmCaptureProcessor);
