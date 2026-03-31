#include "sim/network_accel/NetworkAccelCoordinator.hh"

#include <limits>
#include <sstream>
#include <string>
#include <vector>

#include "base/logging.hh"
#include "sim/eventq.hh"
#include "sim/network_accel/WorkerPool.hh"

namespace gem5
{

namespace
{

thread_local uint32_t threadQueueIndex = std::numeric_limits<uint32_t>::max();

uint32_t
queueIndexFor(EventQueue *eventq)
{
    for (uint32_t i = 0; i < numMainEventQueues; ++i) {
        if (mainEventQueue[i] == eventq) {
            return i;
        }
    }

    panic("Parallel network acceleration saw an unknown event queue");
}

std::string
countSummary(
    const std::unique_ptr<std::atomic<uint64_t>[]> &counts,
    uint32_t count
)
{
    std::ostringstream out;
    for (uint32_t i = 0; i < count; ++i) {
        if (i != 0) {
            out << ",";
        }
        out << i << ":" << counts[i].load(std::memory_order_relaxed);
    }
    return out.str();
}

uint64_t
countFor(
    const std::unique_ptr<std::atomic<uint64_t>[]> &counts,
    uint32_t index
)
{
    return counts[index].load(std::memory_order_relaxed);
}

} // namespace

NetworkAccelMode
networkAccelModeFromString(const std::string &mode)
{
    if (mode == "off") {
        return NetworkAccelMode::Off;
    }
    if (mode == "serial_batched") {
        return NetworkAccelMode::SerialBatched;
    }
    if (mode == "parallel") {
        return NetworkAccelMode::Parallel;
    }

    panic("Unknown network acceleration mode '%s'", mode);
}

NetworkAccelCoordinator &
NetworkAccelCoordinator::instance()
{
    static NetworkAccelCoordinator coordinator;
    return coordinator;
}

void
NetworkAccelCoordinator::configure(const NetworkAccelConfig &config)
{
    panic_if(
        config.workers == 0,
        "Network acceleration worker count must be >= 1"
    );

    _requestedConfig = config;
    _config = config;
    _note.clear();
    _parallelPartitions = 0;
    _runtimeQueueCount = 0;
    _queueEnterCounts.reset();
    _dispatchCounts.reset();
    _workerPool.reset();

    if (config.mode == NetworkAccelMode::Parallel) {
        _config.mode = NetworkAccelMode::Off;
        _config.workers = 1;
        _note = "parallel mode requested but no parallel partition was configured";
    }
}

void
NetworkAccelCoordinator::configure(const std::string &mode, uint32_t workers)
{
    NetworkAccelConfig config;
    config.mode = networkAccelModeFromString(mode);
    config.workers = workers;
    configure(config);
}

void
NetworkAccelCoordinator::reset()
{
    _requestedConfig = {};
    _config = {};
    _note.clear();
    _parallelPartitions = 0;
    _runtimeQueueCount = 0;
    _queueEnterCounts.reset();
    _dispatchCounts.reset();
    _workerPool.reset();
}

void
NetworkAccelCoordinator::activateParallelMode(uint32_t partitions)
{
    panic_if(
        _requestedConfig.mode != NetworkAccelMode::Parallel,
        "Parallel activation requested when network acceleration mode is '%s'",
        _requestedConfig.modeName()
    );

    _workerPool = std::make_unique<WorkerPool>(
        _requestedConfig.workers, partitions
    );
    _parallelPartitions = partitions;

    panic_if(
        _workerPool->workerCount() < 2,
        "Parallel network acceleration requires at least 2 active workers"
    );

    _config.mode = NetworkAccelMode::Parallel;
    _config.workers = _workerPool->workerCount();

    if (_config.workers != _requestedConfig.workers) {
        _note = "parallel mode reduced worker count to " +
                std::to_string(_config.workers) + " for " +
                std::to_string(_parallelPartitions) + " partitions";
    } else {
        _note.clear();
    }
}

const NetworkAccelConfig &
NetworkAccelCoordinator::config() const
{
    return _config;
}

NetworkAccelMode
NetworkAccelCoordinator::mode() const
{
    return _config.mode;
}

uint32_t
NetworkAccelCoordinator::workers() const
{
    return _config.workers;
}

std::string
NetworkAccelCoordinator::modeName() const
{
    return _config.modeName();
}

NetworkAccelMode
NetworkAccelCoordinator::requestedMode() const
{
    return _requestedConfig.mode;
}

uint32_t
NetworkAccelCoordinator::requestedWorkers() const
{
    return _requestedConfig.workers;
}

std::string
NetworkAccelCoordinator::requestedModeName() const
{
    return _requestedConfig.modeName();
}

bool
NetworkAccelCoordinator::downgraded() const
{
    return _requestedConfig.mode != _config.mode ||
           _requestedConfig.workers != _config.workers;
}

const std::string &
NetworkAccelCoordinator::note() const
{
    return _note;
}

uint32_t
NetworkAccelCoordinator::parallelPartitions() const
{
    return _parallelPartitions;
}

std::string
NetworkAccelCoordinator::queueSummary() const
{
    if (!_workerPool) {
        return "";
    }

    return _workerPool->queueSummary();
}

std::string
NetworkAccelCoordinator::activeQueueSummary() const
{
    if (!_queueEnterCounts || _runtimeQueueCount == 0) {
        return "";
    }

    return countSummary(_queueEnterCounts, _runtimeQueueCount);
}

std::string
NetworkAccelCoordinator::dispatchSummary() const
{
    if (!_dispatchCounts || _runtimeQueueCount == 0) {
        return "";
    }

    return countSummary(_dispatchCounts, _runtimeQueueCount);
}

bool
NetworkAccelCoordinator::serialBatchingEnabled() const
{
    return _config.mode == NetworkAccelMode::SerialBatched;
}

uint32_t
NetworkAccelCoordinator::dispatchBatchLimit() const
{
    return 64;
}

void
NetworkAccelCoordinator::beforeSimulation()
{
    if (_config.mode != NetworkAccelMode::Parallel) {
        return;
    }

    panic_if(
        !_workerPool,
        "Parallel network acceleration was enabled without activating a worker pool"
    );
    panic_if(
        simQuantum == 0,
        "Parallel network acceleration requires root.sim_quantum to be set"
    );
    panic_if(
        numMainEventQueues != _workerPool->workerCount() + 1,
        "Parallel network acceleration expected %u main event queues but saw %u",
        _workerPool->workerCount() + 1, numMainEventQueues
    );

    threadQueueIndex = std::numeric_limits<uint32_t>::max();
    _runtimeQueueCount = numMainEventQueues;
    _queueEnterCounts =
        std::make_unique<std::atomic<uint64_t>[]>(_runtimeQueueCount);
    _dispatchCounts =
        std::make_unique<std::atomic<uint64_t>[]>(_runtimeQueueCount);
    for (uint32_t i = 0; i < _runtimeQueueCount; ++i) {
        _queueEnterCounts[i].store(0, std::memory_order_relaxed);
        _dispatchCounts[i].store(0, std::memory_order_relaxed);
    }
}

void
NetworkAccelCoordinator::afterSimulation()
{
    if (_config.mode != NetworkAccelMode::Parallel) {
        return;
    }

    panic_if(
        !_workerPool,
        "Parallel network acceleration completed without a worker pool"
    );
    panic_if(
        !_queueEnterCounts || !_dispatchCounts || _runtimeQueueCount == 0,
        "Parallel network acceleration completed without runtime queue accounting"
    );

    std::vector<bool> expectedQueues(_runtimeQueueCount, false);
    expectedQueues[0] = true;
    for (const uint32_t queue_id : _workerPool->queueIds()) {
        panic_if(
            queue_id >= _runtimeQueueCount,
            "Parallel network acceleration expected queue %u but only saw %u queues",
            queue_id, _runtimeQueueCount
        );
        panic_if(
            expectedQueues[queue_id],
            "Parallel network acceleration queue %u was assigned more than once",
            queue_id
        );
        expectedQueues[queue_id] = true;
    }

    for (uint32_t queue_id = 0; queue_id < _runtimeQueueCount; ++queue_id) {
        const uint64_t entered = countFor(_queueEnterCounts, queue_id);
        const uint64_t dispatched = countFor(_dispatchCounts, queue_id);
        if (expectedQueues[queue_id]) {
            panic_if(
                entered == 0,
                "Parallel network acceleration queue %u never entered the simulation loop",
                queue_id
            );
            panic_if(
                dispatched == 0,
                "Parallel network acceleration queue %u never dispatched an event",
                queue_id
            );
            continue;
        }

        panic_if(
            entered != 0 || dispatched != 0,
            "Parallel network acceleration saw unexpected activity on queue %u",
            queue_id
        );
    }
}

void
NetworkAccelCoordinator::onLoopEnter(EventQueue *eventq, bool main_queue)
{
    if (_config.mode != NetworkAccelMode::Parallel) {
        return;
    }

    threadQueueIndex = queueIndexFor(eventq);
    panic_if(
        main_queue != (threadQueueIndex == 0),
        "Parallel network acceleration saw inconsistent queue role for queue %u",
        threadQueueIndex
    );
    panic_if(
        threadQueueIndex >= _runtimeQueueCount,
        "Parallel network acceleration queue %u exceeds runtime queue count %u",
        threadQueueIndex, _runtimeQueueCount
    );

    _queueEnterCounts[threadQueueIndex].fetch_add(1, std::memory_order_relaxed);
}

void
NetworkAccelCoordinator::beforeDispatch(EventQueue *eventq)
{
    (void)eventq;
}

void
NetworkAccelCoordinator::afterDispatch(EventQueue *eventq, Event *exit_event)
{
    if (_config.mode != NetworkAccelMode::Parallel) {
        return;
    }

    const uint32_t eventqIndex = queueIndexFor(eventq);
    if (threadQueueIndex == std::numeric_limits<uint32_t>::max()) {
        threadQueueIndex = eventqIndex;
    }
    panic_if(
        threadQueueIndex != eventqIndex,
        "Parallel network acceleration dispatch queue changed from %u to %u",
        threadQueueIndex, eventqIndex
    );
    panic_if(
        threadQueueIndex >= _runtimeQueueCount,
        "Parallel network acceleration queue %u exceeds runtime queue count %u",
        threadQueueIndex, _runtimeQueueCount
    );
    _dispatchCounts[threadQueueIndex].fetch_add(1, std::memory_order_relaxed);
    (void)exit_event;
}

} // namespace gem5
