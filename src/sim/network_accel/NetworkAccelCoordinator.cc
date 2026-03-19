#include "sim/network_accel/NetworkAccelCoordinator.hh"

#include <string>

#include "base/logging.hh"
#include "sim/eventq.hh"
#include "sim/network_accel/WorkerPool.hh"

namespace gem5
{

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
}

void
NetworkAccelCoordinator::afterSimulation()
{
}

void
NetworkAccelCoordinator::onLoopEnter(EventQueue *eventq, bool main_queue)
{
    (void)eventq;
    (void)main_queue;
}

void
NetworkAccelCoordinator::beforeDispatch(EventQueue *eventq)
{
    (void)eventq;
}

void
NetworkAccelCoordinator::afterDispatch(EventQueue *eventq, Event *exit_event)
{
    (void)eventq;
    (void)exit_event;
}

} // namespace gem5
