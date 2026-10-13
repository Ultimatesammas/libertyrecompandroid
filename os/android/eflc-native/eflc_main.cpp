// EFLC start-test host. Game-specific GTA IV TU8 hooks are not registered.
// The user supplies the exact disc executable at installation time.
#include "eflc_init.h"
#include <rex/rex_app.h>
#include <rex/filesystem.h>

class EflcStartTest final : public rex::ReXApp {
 public:
  static std::unique_ptr<rex::ui::WindowedApp> Create(rex::ui::WindowedAppContext& context) {
    return std::unique_ptr<EflcStartTest>(new EflcStartTest(context));
  }
 private:
  explicit EflcStartTest(rex::ui::WindowedAppContext& context)
      : rex::ReXApp(context, "EFLC Test", PPCImageConfig) {}
  void OnPreSetup(rex::RuntimeConfig& config) override {
    config.gpu_plugin = "xenos";
  }
  void OnConfigurePaths(rex::PathConfig& paths) override {
    const auto root = rex::filesystem::GetUserFolder() / "EFLC";
    if (paths.game_data_root.empty()) paths.game_data_root = root / "game";
    if (paths.saved_game_root.empty()) paths.saved_game_root = root / "saves";
    // Android passes explicit user/cache/metadata paths in EflcGameActivity.
  }
};
REX_DEFINE_APP(eflc, EflcStartTest::Create)
