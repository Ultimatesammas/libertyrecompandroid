#!/usr/bin/env python3
"""Exercise the actual controller bodies with fake clocks/cvars, not a GPU.

This verifies controller decisions and existing quicksave eligibility only.
It does NOT run GTA IV or verify disk persistence on an Android device.
"""
from pathlib import Path
import argparse
import json
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'glue/rexglue-sdk-main/src/graphics/gta4_native'
GUEST = ROOT / 'glue/rexglue-sdk-main/gta4-recomp/src'


def body(source, name):
    start = source.index('void Gta4NativeGraphicsSystem::' + name + '(')
    left = source.index('{', start)
    depth = 1
    right = left + 1
    while depth:
        depth += (source[right] == '{') - (source[right] == '}')
        right += 1
    return source[start:right]


FIXTURE = r'''
#include "adaptive_frame_budget.h"
#include "gta4_quicksave_policy.h"
#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <map>
#include <sstream>
#include <string>
#include <type_traits>
using namespace rex::graphics::gta4_native;
namespace rex::cvar {
std::map<std::string,std::string> values;
std::string GetFlagByName(const char* name) { return values.at(name); }
void SetFlagByName(const char* name, const std::string& value) { values[name]=value; }
template<class T> T Query(const char* name) { return static_cast<T>(std::stoul(values.at(name))); }
}
namespace rex::chrono {
uint64_t now=1000000;
struct Clock {
 static uint64_t QueryHostTickCount() { return now; }
 static uint64_t QueryHostTickFrequency() { return 1000000; }
};
}
namespace fmt {
std::string format(const char*,double number) {
 std::ostringstream out;out<<std::fixed<<std::setprecision(3)<<number;return out.str();
}
}
#define REXCVAR_GET(name) rex::cvar::Query<uint32_t>(#name)
#define REX_PLATFORM_ANDROID 0
class Gta4NativeGraphicsSystem {
public:
 void UpdateDynamicDrawDistance();
 void UpdateFpsGuard(double,uint64_t,uint64_t);
 void ApplyFpsGuardLevel(uint32_t);
 uint32_t dynamic_draw_distance_target_fps_=0;
 double dynamic_draw_distance_factor_=1.0,dynamic_draw_distance_published_=1.0;
 double dynamic_draw_distance_interval_ms_=33.3;
 uint64_t dynamic_draw_distance_last_tick_=0;
 uint32_t dynamic_draw_distance_window_frames_=0;
 double dynamic_draw_distance_window_ms_=0;
 std::array<double,3> dynamic_draw_distance_window_fps_{30,30,30};
 uint32_t dynamic_draw_distance_windows_since_drop_=1000;
 uint32_t fps_guard_level_=0,fps_guard_applied_level_=UINT32_MAX;
 uint64_t fps_guard_changed_tick_=0,fps_guard_slow_since_tick_=0,fps_guard_fast_since_tick_=0;
};
'''

SCENARIOS = r'''
void reset(uint32_t limit) {
 rex::chrono::now=1000000;
 rex::cvar::values={{"gta4_frame_limit",std::to_string(limit)},
 {"gta4_dynamic_draw_distance","true"},{"gta4_dynamic_draw_distance_min","0.80"},
 {"gta4_draw_distance_dynamic_factor","1.000"},{"gta4_fps_guard","0"}};
}
void run(Gta4NativeGraphicsSystem& g,double seconds,double fps) {
 const uint64_t step=static_cast<uint64_t>(std::round(1000000.0/fps));
 for(int i=0;i<static_cast<int>(std::ceil(seconds*fps));++i) {
  rex::chrono::now+=step;g.UpdateDynamicDrawDistance();
 }
}
int main() {
 int cases=0;
 reset(30);{Gta4NativeGraphicsSystem g;run(g,6,45);
 assert(g.dynamic_draw_distance_factor_==1.0);++cases;}
 reset(60);{Gta4NativeGraphicsSystem g;run(g,6,45);
 assert(g.dynamic_draw_distance_factor_<1.0);++cases;}
 reset(60);{Gta4NativeGraphicsSystem g;run(g,30,20);
 assert(std::abs(g.dynamic_draw_distance_factor_-0.8)<1e-9);++cases;}
 reset(60);{Gta4NativeGraphicsSystem g;g.dynamic_draw_distance_factor_=0.8;
 g.dynamic_draw_distance_published_=0.8;run(g,12,58);
 assert(g.dynamic_draw_distance_factor_>0.8);++cases;}
 reset(30);{Gta4NativeGraphicsSystem g;run(g,3,24);
 rex::cvar::values["gta4_frame_limit"]="60";g.UpdateDynamicDrawDistance();
 assert(g.dynamic_draw_distance_target_fps_==60);
 assert(g.dynamic_draw_distance_window_frames_==0);
 assert(g.dynamic_draw_distance_window_fps_[0]==60);++cases;}
 reset(60);{Gta4NativeGraphicsSystem g;run(g,6,45);
 rex::cvar::values["gta4_dynamic_draw_distance"]="false";g.UpdateDynamicDrawDistance();
 assert(g.dynamic_draw_distance_factor_==1.0);
 assert(rex::cvar::values["gta4_draw_distance_dynamic_factor"]=="1.000");
 rex::cvar::values["gta4_dynamic_draw_distance"]="true";run(g,1,60);
 assert(g.dynamic_draw_distance_factor_==1.0);++cases;}
 reset(60);{Gta4NativeGraphicsSystem g;g.UpdateDynamicDrawDistance();
 for(int i=0;i<8;++i){rex::chrono::now+=150000;g.UpdateDynamicDrawDistance();}
 assert(g.dynamic_draw_distance_window_fps_[0]<7.0);++cases;}
 reset(60);{Gta4NativeGraphicsSystem g;g.UpdateDynamicDrawDistance();
 rex::chrono::now+=300000;g.UpdateDynamicDrawDistance();
 assert(g.dynamic_draw_distance_window_frames_==0);++cases;}
 reset(60);{Gta4NativeGraphicsSystem g;rex::cvar::values["gta4_fps_guard"]="3";
 run(g,6,40);assert(g.fps_guard_level_>0);
 assert(rex::cvar::values["gta4_shadow_distance_guard_factor"]=="1.0");++cases;}
 reset(0);{Gta4NativeGraphicsSystem g;g.UpdateDynamicDrawDistance();
 assert(g.dynamic_draw_distance_target_fps_==30);++cases;}
 {gta4::quicksave::Conditions c{.known_program=true,.player_ready=true,.signed_in=true};
 assert(gta4::quicksave::CanSave(c)==gta4::quicksave::Denial::kNone);
 c.signed_in=false;assert(gta4::quicksave::CanSave(c)==gta4::quicksave::Denial::kUnavailable);
 c.signed_in=true;c.busy=true;
 assert(gta4::quicksave::CanSave(c)==gta4::quicksave::Denial::kBusy);
 ++cases;}
 std::cout<<cases<<" controller/quicksave eligibility scenarios passed\n";
}
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--compiler', default='g++')
    args = parser.parse_args()
    source = (NATIVE / 'graphics_system.cpp').read_text(encoding='utf-8')
    methods = '\n'.join(body(source, name) for name in
                        ['UpdateDynamicDrawDistance', 'ApplyFpsGuardLevel', 'UpdateFpsGuard'])
    with tempfile.TemporaryDirectory(prefix='thor-tests-') as temp:
        temp = Path(temp)
        cpp = temp / 'controller_test.cpp'
        cpp.write_text(FIXTURE + methods + SCENARIOS, encoding='utf-8')
        exe = temp / 'controller_test'
        subprocess.run([args.compiler, '-std=c++20', '-Wall', '-Wextra', '-Werror',
                        '-UNDEBUG', '-I' + str(NATIVE), '-I' + str(GUEST),
                        str(cpp), '-o', str(exe)], check=True)
        subprocess.run([str(exe)], check=True)
    print(json.dumps({'controller_logic':'passed', 'android_build':'not tested here',
                      'in_game_saving':'requires device acceptance'}))


if __name__ == '__main__':
    main()
