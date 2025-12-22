class PCMProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this.bufferSize = 1600; // Will be overridden by message
        this.buffer = new Float32Array(this.bufferSize);
        this.bufferIndex = 0;

        // Listen for configuration from main thread
        this.port.onmessage = (event) => {
            if (event.data.type === 'config') {
                this.bufferSize = event.data.bufferSize;
                this.buffer = new Float32Array(this.bufferSize);
                this.bufferIndex = 0;
            }
        };
    }

    process(inputs, outputs, parameters) {
        const input = inputs[0];
        if (input && input.length > 0) {
            const channelData = input[0]; // mono - first channel

            for (let i = 0; i < channelData.length; i++) {
                this.buffer[this.bufferIndex++] = channelData[i];

                if (this.bufferIndex >= this.bufferSize) {
                    // Buffer full - send to main thread
                    this.port.postMessage({
                        type: 'audio',
                        samples: this.buffer.slice()
                    });
                    this.bufferIndex = 0;
                }
            }
        }
        return true; // Keep processor alive
    }
}

registerProcessor('pcm-processor', PCMProcessor);
