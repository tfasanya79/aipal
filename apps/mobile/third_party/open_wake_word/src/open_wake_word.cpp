#include "open_wake_word.h"

#include <condition_variable>
#include <iostream>
#include <mutex>
#include <numeric>
#include <string>
#include <thread>
#include <vector>
#include <atomic>
#include <sstream>
#include <algorithm>

#include <onnxruntime_cxx_api.h>

using namespace std;

// Model settings constants
const string instanceName = "openWakeWordFFI";
const size_t chunkSamples = 1280; // 80 ms
const size_t numMels = 32;
const size_t embWindowSize = 76; // 775 ms
const size_t embStepSize = 8;    // 80 ms
const size_t embFeatures = 96;
const size_t wwFeatures = 16;

struct Settings {
  string melModelPath;
  string embModelPath;
  vector<string> wwModelPaths;

  size_t stepFrames = 4;
  size_t frameSize = 4 * chunkSamples; // 5120

  float threshold = 0.5f;
  int triggerLevel = 4;
  int refractory = 20;

  Ort::SessionOptions options;
};

struct EngineState {
  Ort::Env env;

  vector<mutex> mutFeatures;
  vector<condition_variable> cvFeatures;
  vector<bool> featuresExhausted;
  vector<bool> featuresReady;

  bool samplesExhausted = false;
  bool melsExhausted = false;
  bool samplesReady = false;
  bool melsReady = false;

  mutex mutSamples, mutMels, mutReady, mutOutput;
  condition_variable cvSamples, cvMels, cvReady;

  size_t numReady = 0;
  std::atomic<bool> loadFailed{false};
  std::string loadError;

  std::atomic<float> latestProbability{0.0f};
  std::atomic<bool> isActivated{false};

  EngineState(size_t numWakeWords) :
        mutFeatures(numWakeWords),
        cvFeatures(numWakeWords),
        featuresExhausted(numWakeWords),
        featuresReady(numWakeWords) {
    env = Ort::Env(OrtLoggingLevel::ORT_LOGGING_LEVEL_WARNING, instanceName.c_str());
    env.DisableTelemetryEvents();
    fill(featuresExhausted.begin(), featuresExhausted.end(), false);
    fill(featuresReady.begin(), featuresReady.end(), false);
  }
};

static Settings* g_settings = nullptr;
static EngineState* g_state = nullptr;

// Persists across oww_destroy() (which frees g_state) so the Dart layer can
// query the reason for the most recent init failure after cleanup runs.
static std::string g_lastError;

static vector<float> g_floatSamples;
static vector<float> g_mels;
static vector<vector<float>> g_features;

static thread* g_melThread = nullptr;
static thread* g_featuresThread = nullptr;
static vector<thread*> g_wwThreads;

std::wstring to_wstring(const std::string& str) {
    return std::wstring(str.begin(), str.end());
}

// Thread 1: Audio -> Mels
void audioToMels() {
 try {
  Ort::AllocatorWithDefaultOptions allocator;
  auto memoryInfo = Ort::MemoryInfo::CreateCpu(
      OrtAllocatorType::OrtArenaAllocator, OrtMemType::OrtMemTypeDefault);

  auto melSession = Ort::Session(g_state->env,
#ifdef _WIN32
    to_wstring(g_settings->melModelPath).c_str(),
#else
    g_settings->melModelPath.c_str(),
#endif
  g_settings->options);

  vector<int64_t> samplesShape{1, (int64_t)g_settings->frameSize};

  auto melInputName = melSession.GetInputNameAllocated(0, allocator);
  vector<const char *> melInputNames{melInputName.get()};

  auto melOutputName = melSession.GetOutputNameAllocated(0, allocator);
  vector<const char *> melOutputNames{melOutputName.get()};

  vector<float> todoSamples;

  {
    unique_lock<mutex> lockReady(g_state->mutReady);
    g_state->numReady += 1;
    g_state->cvReady.notify_one();
  }

  Ort::RunOptions runOptions{nullptr};

  while (true) {
    {
      unique_lock<mutex> lockSamples{g_state->mutSamples};
      g_state->cvSamples.wait(lockSamples, [] { return g_state->samplesReady; });
      if (g_state->samplesExhausted && g_floatSamples.empty()) {
        break;
      }
      copy(g_floatSamples.begin(), g_floatSamples.end(), back_inserter(todoSamples));
      g_floatSamples.clear();

      if (!g_state->samplesExhausted) {
        g_state->samplesReady = false;
      }
    }

    while (todoSamples.size() >= g_settings->frameSize) {
      Ort::Value melInputTensor = Ort::Value::CreateTensor<float>(
          memoryInfo, todoSamples.data(), g_settings->frameSize,
          samplesShape.data(), samplesShape.size());

      auto melOutputTensors =
          melSession.Run(runOptions, melInputNames.data(),
                         &melInputTensor, 1,
                         melOutputNames.data(), melOutputNames.size());

      const auto &melOut = melOutputTensors.front();
      const auto melInfo = melOut.GetTensorTypeAndShapeInfo();
      const auto melShape = melInfo.GetShape();

      const float *melData = melOut.GetTensorData<float>();
      size_t melCount = accumulate(melShape.begin(), melShape.end(), 1, multiplies<size_t>());

      {
        unique_lock<mutex> lockMels{g_state->mutMels};
        g_mels.reserve(g_mels.size() + melCount);
        for (size_t i = 0; i < melCount; i++) {
          g_mels.push_back((melData[i] / 10.0f) + 2.0f);
        }
        g_state->melsReady = true;
        g_state->cvMels.notify_one();
      }

      todoSamples.erase(todoSamples.begin(), todoSamples.begin() + g_settings->frameSize);
    }
  }
 } catch (const std::exception& e) {
  unique_lock<mutex> lockReady(g_state->mutReady);
  if (!g_state->loadFailed) {
    g_state->loadFailed = true;
    g_state->loadError = string("mel thread failed: ") + e.what();
  }
  g_state->numReady += 1;
  g_state->cvReady.notify_one();
 }
}

// Thread 2: Mels -> Features
void melsToFeatures() {
 try {
  Ort::AllocatorWithDefaultOptions allocator;
  auto memoryInfo = Ort::MemoryInfo::CreateCpu(
      OrtAllocatorType::OrtArenaAllocator, OrtMemType::OrtMemTypeDefault);

  auto embSession = Ort::Session(g_state->env, 
#ifdef _WIN32
    to_wstring(g_settings->embModelPath).c_str(),
#else
    g_settings->embModelPath.c_str(), 
#endif
  g_settings->options);

  vector<int64_t> embShape{1, (int64_t)embWindowSize, (int64_t)numMels, 1};

  auto embInputName = embSession.GetInputNameAllocated(0, allocator);
  vector<const char *> embInputNames{embInputName.get()};

  auto embOutputName = embSession.GetOutputNameAllocated(0, allocator);
  vector<const char *> embOutputNames{embOutputName.get()};

  vector<float> todoMels;
  size_t melFrames = 0;

  {
    unique_lock<mutex> lockReady(g_state->mutReady);
    g_state->numReady += 1;
    g_state->cvReady.notify_one();
  }

  Ort::RunOptions runOptions{nullptr};

  while (true) {
    {
      unique_lock<mutex> lockMels{g_state->mutMels};
      g_state->cvMels.wait(lockMels, [] { return g_state->melsReady; });
      if (g_state->melsExhausted && g_mels.empty()) {
        break;
      }
      copy(g_mels.begin(), g_mels.end(), back_inserter(todoMels));
      g_mels.clear();

      if (!g_state->melsExhausted) {
        g_state->melsReady = false;
      }
    }

    melFrames = todoMels.size() / numMels;
    while (melFrames >= embWindowSize) {
      Ort::Value embInputTensor = Ort::Value::CreateTensor<float>(
          memoryInfo, todoMels.data(), embWindowSize * numMels, embShape.data(),
          embShape.size());

      auto embOutputTensors =
          embSession.Run(runOptions, embInputNames.data(),
                         &embInputTensor, 1,
                         embOutputNames.data(), embOutputNames.size());

      const auto &embOut = embOutputTensors.front();
      const auto embOutInfo = embOut.GetTensorTypeAndShapeInfo();
      const auto embOutShape = embOutInfo.GetShape();

      const float *embOutData = embOut.GetTensorData<float>();
      size_t embOutCount = accumulate(embOutShape.begin(), embOutShape.end(), 1, multiplies<size_t>());

      for (size_t i = 0; i < g_features.size(); i++) {
        unique_lock<mutex> lockFeatures{g_state->mutFeatures[i]};
        g_features[i].reserve(g_features[i].size() + embOutCount);
        copy(embOutData, embOutData + embOutCount, back_inserter(g_features[i]));
        g_state->featuresReady[i] = true;
        g_state->cvFeatures[i].notify_one();
      }

      todoMels.erase(todoMels.begin(), todoMels.begin() + (embStepSize * numMels));
      melFrames = todoMels.size() / numMels;
    }
  }
 } catch (const std::exception& e) {
  unique_lock<mutex> lockReady(g_state->mutReady);
  if (!g_state->loadFailed) {
    g_state->loadFailed = true;
    g_state->loadError = string("embedding thread failed: ") + e.what();
  }
  g_state->numReady += 1;
  g_state->cvReady.notify_one();
 }
}

// Thread 3: Features -> Output Probability
void featuresToOutput(size_t wwIdx) {
 try {
  Ort::AllocatorWithDefaultOptions allocator;
  auto memoryInfo = Ort::MemoryInfo::CreateCpu(
      OrtAllocatorType::OrtArenaAllocator, OrtMemType::OrtMemTypeDefault);

  string wwModelPath = g_settings->wwModelPaths[wwIdx];
  auto wwSession = Ort::Session(g_state->env, 
#ifdef _WIN32
    to_wstring(wwModelPath).c_str(),
#else
    wwModelPath.c_str(), 
#endif
  g_settings->options);

  vector<int64_t> wwShape{1, (int64_t)wwFeatures, (int64_t)embFeatures};

  auto wwInputName = wwSession.GetInputNameAllocated(0, allocator);
  vector<const char *> wwInputNames{wwInputName.get()};

  auto wwOutputName = wwSession.GetOutputNameAllocated(0, allocator);
  vector<const char *> wwOutputNames{wwOutputName.get()};

  vector<float> todoFeatures;
  size_t numBufferedFeatures = 0;
  int activation = 0;

  {
    unique_lock<mutex> lockReady(g_state->mutReady);
    g_state->numReady += 1;
    g_state->cvReady.notify_one();
  }

  Ort::RunOptions runOptions{nullptr};

  while (true) {
    {
      unique_lock<mutex> lockFeatures{g_state->mutFeatures[wwIdx]};
      g_state->cvFeatures[wwIdx].wait(lockFeatures, [&, wwIdx] { return g_state->featuresReady[wwIdx]; });
      if (g_state->featuresExhausted[wwIdx] && g_features[wwIdx].empty()) {
        break;
      }
      copy(g_features[wwIdx].begin(), g_features[wwIdx].end(), back_inserter(todoFeatures));
      g_features[wwIdx].clear();

      if (!g_state->featuresExhausted[wwIdx]) {
        g_state->featuresReady[wwIdx] = false;
      }
    }

    numBufferedFeatures = todoFeatures.size() / embFeatures;
    while (numBufferedFeatures >= wwFeatures) {
      Ort::Value wwInputTensor = Ort::Value::CreateTensor<float>(
          memoryInfo, todoFeatures.data(), wwFeatures * embFeatures,
          wwShape.data(), wwShape.size());

      auto wwOutputTensors =
          wwSession.Run(runOptions, wwInputNames.data(),
                        &wwInputTensor, 1, wwOutputNames.data(), 1);

      const auto &wwOut = wwOutputTensors.front();
      const auto wwOutInfo = wwOut.GetTensorTypeAndShapeInfo();
      const auto wwOutShape = wwOutInfo.GetShape();
      const float *wwOutData = wwOut.GetTensorData<float>();
      size_t wwOutCount = accumulate(wwOutShape.begin(), wwOutShape.end(), 1, multiplies<size_t>());

      for (size_t i = 0; i < wwOutCount; i++) {
        float probability = wwOutData[i];
        
        // We will just update global probability mapping to max to keep FFI simple for now
        float currentMax = g_state->latestProbability.load();
        if (probability > currentMax) {
           g_state->latestProbability.store(probability);
        }

        if (probability > g_settings->threshold) {
          activation++;
          if (activation >= g_settings->triggerLevel) {
            g_state->isActivated.store(true);
            activation = -g_settings->refractory;
          }
        } else {
          if (activation > 0) {
            activation = max(0, activation - 1);
          } else {
            activation = min(0, activation + 1);
          }
        }
      }

      todoFeatures.erase(todoFeatures.begin(), todoFeatures.begin() + (1 * embFeatures));
      numBufferedFeatures = todoFeatures.size() / embFeatures;
    }
  }
 } catch (const std::exception& e) {
  unique_lock<mutex> lockReady(g_state->mutReady);
  if (!g_state->loadFailed) {
    g_state->loadFailed = true;
    g_state->loadError = string("wake word model thread failed: ") + e.what();
  }
  g_state->numReady += 1;
  g_state->cvReady.notify_one();
 }
}

extern "C" {

int oww_init(const char* mel_model_path, const char* emb_model_path, const char* ww_model_paths_csv) {
  if (g_settings) oww_destroy();
  g_lastError.clear();

  try {
    g_settings = new Settings();
    g_settings->melModelPath = mel_model_path;
    g_settings->embModelPath = emb_model_path;
    
    // Parse comma separated wake word models
    string paths(ww_model_paths_csv);
    stringstream ss(paths);
    string item;
    while (getline(ss, item, ',')) {
      if (!item.empty()) {
        g_settings->wwModelPaths.push_back(item);
      }
    }

    if (g_settings->wwModelPaths.empty()) {
      g_lastError = "No wake word model paths provided";
      return -1;
    }

    g_settings->options.SetIntraOpNumThreads(1);
    g_settings->options.SetInterOpNumThreads(1);
    g_settings->options.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);

    size_t numModels = g_settings->wwModelPaths.size();
    g_state = new EngineState(numModels);
    g_features.resize(numModels);

    g_melThread = new thread(audioToMels);
    g_featuresThread = new thread(melsToFeatures);
    
    for (size_t i = 0; i < numModels; i++) {
      g_wwThreads.push_back(new thread(featuresToOutput, i));
    }

    // Block until all threads have loaded models (or one signals failure)
    size_t expectedReady = 2 + numModels;
    bool failed = false;
    {
      unique_lock<mutex> lockReady(g_state->mutReady);
      g_state->cvReady.wait(lockReady, [&] {
        return g_state->numReady == expectedReady || g_state->loadFailed.load();
      });
      failed = g_state->loadFailed.load();
    }
    if (failed) {
      // A background thread failed to load its model (e.g. incompatible
      // ONNX op set on this device). Clean up gracefully instead of
      // crashing or leaving half-initialized state, and report failure
      // so the Dart layer can fall back to a known-working model.
      g_lastError = g_state->loadError;
      oww_destroy();
      return -1;
    }
    return 0; // Success
  } catch (const std::exception& e) {
    g_lastError = e.what();
    return -1; // Error
  }
}

void oww_process_audio(const int16_t* audio_data, int length) {
  if (!g_state) return;

  {
    unique_lock<mutex> lockSamples{g_state->mutSamples};
    g_floatSamples.reserve(g_floatSamples.size() + length);
    for(int i = 0; i < length; i++) {
      g_floatSamples.push_back((float)audio_data[i]);
    }
    g_state->samplesReady = true;
    g_state->cvSamples.notify_one();
  }
}

float oww_get_probability() {
  if (!g_state) return 0.0f;
  return g_state->latestProbability.exchange(0.0f); // Reset so it doesn't get stuck at max
}

bool oww_is_activated() {
  if (!g_state) return false;
  return g_state->isActivated.exchange(false); // Clear activation after reading
}

// Returns the reason the most recent oww_init() call failed, or an empty
// string if the last init succeeded (or none has run yet). The returned
// pointer is owned by the native side and only valid until the next
// oww_init() call; callers should copy it immediately if needed.
const char* oww_get_last_error() {
  return g_lastError.c_str();
}

void oww_destroy() {
  if (!g_state) return;

  {
    unique_lock<mutex> lockSamples{g_state->mutSamples};
    g_state->samplesExhausted = true;
    g_state->samplesReady = true;
    g_state->cvSamples.notify_one();
  }
  if (g_melThread) { g_melThread->join(); delete g_melThread; g_melThread = nullptr; }

  {
    unique_lock<mutex> lockMels{g_state->mutMels};
    g_state->melsExhausted = true;
    g_state->melsReady = true;
    g_state->cvMels.notify_one();
  }
  if (g_featuresThread) { g_featuresThread->join(); delete g_featuresThread; g_featuresThread = nullptr; }

  for (size_t i = 0; i < g_wwThreads.size(); i++) {
    {
      unique_lock<mutex> lockFeatures{g_state->mutFeatures[i]};
      g_state->featuresExhausted[i] = true;
      g_state->featuresReady[i] = true;
      g_state->cvFeatures[i].notify_one();
    }
    if (g_wwThreads[i]) { 
        g_wwThreads[i]->join(); 
        delete g_wwThreads[i]; 
    }
  }
  g_wwThreads.clear();

  delete g_state;
  g_state = nullptr;

  delete g_settings;
  g_settings = nullptr;
}

} // extern "C"
