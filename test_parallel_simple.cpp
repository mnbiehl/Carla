/*
 * Simple test for Parallel Plugin Processing POC
 */

#include <cstdio>
#include <cstring>
#include <chrono>
#include <thread>

// Simple test without including Carla headers to verify the concept
class SimpleParallelTest {
public:
    static void processPlugin(int id, const float* input, float* output, int frames) {
        // Simulate plugin processing
        for (int i = 0; i < frames; ++i) {
            output[i] = input[i] * 0.5f; // Simple gain
        }
        // Simulate some processing time
        std::this_thread::sleep_for(std::chrono::microseconds(100));
    }
    
    static void testParallel() {
        const int frames = 512;
        const int numPlugins = 3;
        
        // Input and output buffers for each plugin
        float inputs[numPlugins][frames];
        float outputs[numPlugins][frames];
        
        // Fill inputs with test data
        for (int p = 0; p < numPlugins; ++p) {
            for (int i = 0; i < frames; ++i) {
                inputs[p][i] = 0.1f * (p + 1);
            }
        }
        
        printf("Testing parallel processing with %d plugins...\n", numPlugins);
        
        // Sequential processing
        auto seqStart = std::chrono::high_resolution_clock::now();
        for (int p = 0; p < numPlugins; ++p) {
            processPlugin(p, inputs[p], outputs[p], frames);
        }
        auto seqEnd = std::chrono::high_resolution_clock::now();
        auto seqDuration = std::chrono::duration_cast<std::chrono::microseconds>(seqEnd - seqStart).count();
        
        printf("Sequential processing took: %ld microseconds\n", seqDuration);
        
        // Parallel processing
        auto parStart = std::chrono::high_resolution_clock::now();
        std::thread threads[numPlugins];
        
        for (int p = 0; p < numPlugins; ++p) {
            threads[p] = std::thread(processPlugin, p, inputs[p], outputs[p], frames);
        }
        
        for (int p = 0; p < numPlugins; ++p) {
            threads[p].join();
        }
        
        auto parEnd = std::chrono::high_resolution_clock::now();
        auto parDuration = std::chrono::duration_cast<std::chrono::microseconds>(parEnd - parStart).count();
        
        printf("Parallel processing took: %ld microseconds\n", parDuration);
        printf("Speedup: %.2fx\n", (float)seqDuration / parDuration);
        
        // Merge outputs (simple sum)
        float finalOutput[frames];
        memset(finalOutput, 0, sizeof(finalOutput));
        
        for (int i = 0; i < frames; ++i) {
            for (int p = 0; p < numPlugins; ++p) {
                finalOutput[i] += outputs[p][i] / numPlugins;
            }
        }
        
        printf("First output sample: %f\n", finalOutput[0]);
        printf("Test completed successfully!\n");
    }
};

int main() {
    printf("=== Simple Parallel Processing Test ===\n");
    SimpleParallelTest::testParallel();
    return 0;
}