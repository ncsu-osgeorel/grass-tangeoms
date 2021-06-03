# -*- coding: utf-8 -*-
"""
@brief activities

This program is free software under the GNU General Public License
(>=v2). Read the file COPYING that comes with GRASS for details.

@author: Anna Petrasova (akratoc@ncsu.edu)
"""
import os
import imp
import datetime
import json
import traceback
import wx
import wx.lib.newevent
import wx.lib.filebrowsebutton as filebrowse
from wx.lib.wordwrap import wordwrap

from grass.exceptions import CalledModuleError, ScriptError
from grass.pydispatch.signal import Signal

from tangible_utils import get_environment
try:
    from activities_profile import ProfileFrame
except ImportError:
    ProfileFrame = None

from activities_dashboard import MultipleDashboardFrame

# lazy importing activities_slides

updateProfile, EVT_UPDATE_PROFILE = wx.lib.newevent.NewEvent()
updateDisplay, EVT_UPDATE_DISPLAY = wx.lib.newevent.NewEvent()


class ActivitiesPanel(wx.Panel):
    def __init__(self, parent, giface, settings, scaniface):
        wx.Panel.__init__(self, parent)
        self.group = None
        self.env = None
        self.giface = giface
        self.parent = parent
        self.settings = settings
        self.scaniface = scaniface
        self.current = 0
        self.currentSubtask = 0
        self.startTime = 0
        self.endTime = 0
        self.settingsChanged = Signal('ActivitiesPanel.settingsChanged')
        self.configFile = ''
        self.tasks = []
        self.configuration = {}
        self.profileFrame = None
        self.dashboardFrame = None
        self.handsoff = None
        self.slides = None
        self.scaniface.additionalParams4Analyses = {'subTask': self.currentSubtask}
        self._processingSubTask = False

        # we want to start in pause mode to not capture any data
        self.scaniface.pause = True
        if 'activities' not in self.settings:
            self.settings['activities'] = {}
            self.settings['activities']['config'] = ''
        else:
            self.configFile = self.settings['activities']['config']

        self.configPath = filebrowse.FileBrowseButton(self, labelText='Configuration:', fileMask="JSON file (*.json)|*.json",
                                                      changeCallback=self._loadConfiguration)
        self.configPath.SetValue(self.configFile, 0)

        self.title = wx.StaticText(self, label='')
        self.title.SetFont(wx.Font(18, wx.DEFAULT, wx.NORMAL, wx.BOLD))
        self.buttonBack = wx.Button(self, label='  <  ')
        self.buttonForward = wx.Button(self, label='  >  ')
        self.buttonBack.Bind(wx.EVT_BUTTON, self.OnBack)
        self.buttonForward.Bind(wx.EVT_BUTTON, self.OnForward)
        self.buttonStart = wx.Button(self, label='Start activity')
        self.buttonCalibrate = wx.Button(self, size=(150, -1), label='Calibrate')
        self.buttonStop = wx.Button(self, label='End activity')
        self.buttonStart.Bind(wx.EVT_BUTTON, self.OnStart)
        self.buttonCalibrate.Bind(wx.EVT_BUTTON, lambda evt: self.Calibrate(startTask=False))
        self.buttonStop.Bind(wx.EVT_BUTTON, self.OnStop)
        self.timeText = wx.StaticText(self, label='00:00', style=wx.ALIGN_CENTRE)
        self.timeText.SetFont(wx.Font(15, wx.FONTFAMILY_TELETYPE, wx.NORMAL, wx.FONTWEIGHT_BOLD))
        self.slidesStatus = wx.StaticText(self, label='Slides off', style=wx.ALIGN_CENTRE | wx.ALIGN_CENTRE_HORIZONTAL)
        self.slidesStatus.SetFont(wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL))

        self.buttonNext = wx.Button(self, label='Next')
        self.buttonNext.Bind(wx.EVT_BUTTON, self.OnSubtask)

        self.instructions = wx.StaticText(self)

        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.OnTimer)

        self.mainSizer = wx.BoxSizer(wx.VERTICAL)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.configPath, proportion=1, flag=wx.ALIGN_CENTER_VERTICAL, border=5)
        self.mainSizer.Add(sizer, flag=wx.EXPAND | wx.ALL, border=5)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.title, proportion=1, flag=wx.ALIGN_CENTER_VERTICAL, border=5)
        sizer.Add(self.buttonBack, proportion=0, flag=wx.ALIGN_CENTER_VERTICAL, border=5)
        sizer.Add(self.buttonForward, proportion=0, flag=wx.ALIGN_CENTER_VERTICAL, border=5)
        self.mainSizer.Add(sizer, flag=wx.EXPAND | wx.ALL, border=5)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.buttonCalibrate, proportion=0, flag=wx.ALIGN_CENTER_VERTICAL, border=5)
        self.mainSizer.Add(sizer, flag=wx.EXPAND | wx.ALL, border=5)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.buttonStart, proportion=1, flag=wx.ALIGN_CENTER_VERTICAL, border=5)
#        sizer.Add(self.buttonPause, proportion=1, flag=wx.EXPAND | wx.ALIGN_CENTER_VERTICAL, border=5)
        sizer.Add(self.buttonStop, proportion=1, flag=wx.ALIGN_CENTER_VERTICAL, border=5)
        sizer.Add(self.slidesStatus, proportion=0, flag=wx.ALIGN_CENTER | wx.LEFT | wx.RIGHT, border=10)
        sizer.Add(self.timeText, proportion=0, flag=wx.ALIGN_CENTER | wx.LEFT, border=5)
        self.mainSizer.Add(sizer, flag=wx.EXPAND | wx.ALL, border=5)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.buttonNext, proportion=1, flag=wx.ALIGN_CENTER_VERTICAL, border=5)
        self.mainSizer.Add(sizer, flag=wx.EXPAND | wx.ALL, border=5)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.instructions, proportion=1, flag=wx.ALIGN_CENTER_VERTICAL, border=5)
        self.mainSizer.Add(sizer, flag=wx.EXPAND | wx.ALL, border=5)
        self.SetSizer(self.mainSizer)
        self.mainSizer.Fit(self)
        self.buttonNext.Hide()
        self.Layout()

        self.Bind(EVT_UPDATE_PROFILE, self.OnProfileUpdate)
        self.Bind(EVT_UPDATE_DISPLAY, self.OnDisplayUpdate)

        self._init()

    def IsStandalone(self):
        """If TL plugin runs standalone without GUI"""
        if self.giface.GetLayerTree():
            return False
        return True

    def _init(self):
        if self.configFile:
            try:
                with open(self.configFile, 'r') as f:
                    try:
                        self.configuration = json.load(f)
                        self.tasks = self.configuration['tasks']
                        # this should reset the analysis file only when configuration is successfully loaded
                        self.settings['analyses']['file'] = ''
                    except ValueError:
                        self.configFile = None
            except IOError:
                self.configFile = None

        self.current = 0
        if self.tasks:
            self.title.SetLabel(self.tasks[self.current]['title'])
            self.buttonBack.Enable(False)
            self.buttonForward.Enable(True)
            self.timeText.SetLabel('00:00')
            self.slidesStatus.Show(bool('slides' in self.configuration and self.configuration['slides']))
            self.instructions.SetLabel(self._getInstructions())
        else:
            self._enableGUI(False)
        if self.configFile:
            self.buttonNext.Show('sublayers' in self.tasks[self.current])
            self.buttonCalibrate.Show('calibrate' in self.tasks[self.current])

        self._bindUserStop()
        self.Layout()

    def _enableGUI(self, enable):
        self.buttonBack.Enable(enable)
        self.buttonForward.Enable(enable)
        self.buttonStart.Enable(enable)
        self.buttonCalibrate.Enable(enable)
        self.buttonStop.Enable(enable)
        self.slidesStatus.Enable(enable)
        self.timeText.Enable(enable)
        self.title.Enable(enable)
        self.instructions.Show(enable)

    def _bindUserStop(self):
        # if standalone, no binding can be done
        windows = [wx.GetTopLevelParent(self)]
        if not self.IsStandalone():
            windows.append(self.giface.lmgr)
            windows.extend([mapw for mapw in self.giface.GetAllMapDisplays()])
        bindings = {"stopTask": self.OnUserStop, 'scanOnce': self.OnScanOnce, 'taskNext': self.OnNextTask,
                    'taskPrevious': self.OnPreviousTask, 'startTask': self.StartAutomated}
        if "keyboard_events" in self.configuration:
            items = []
            for eventName in self.configuration['keyboard_events']:
                eventId = wx.NewId()
                items.append((wx.ACCEL_NORMAL, self.configuration['keyboard_events'][eventName], eventId))
                for win in windows:
                    win.Bind(wx.EVT_MENU, bindings.get(eventName, lambda evt: self.CustomAction(eventName)), id=eventId)
            accel_tbl = wx.AcceleratorTable(items)
            for win in windows:
                win.SetAcceleratorTable(accel_tbl)

    def CustomAction(self, eventName):
        env = get_environment(rast=self.settings['output']['scan'])  # noqa: F841
        myanalyses, functions = self._reloadAnalysisFile(funcPrefix=eventName)

        for func in functions:
            try:
                exec('myanalyses.' + func + "(eventHandler=wx.GetTopLevelParent(self), env=env)")
            except (CalledModuleError, Exception, ScriptError):
                print(traceback.print_exc())

    def OnNextTask(self, event):
        if self.timer.IsRunning():
            self.OnStop(event=None)
        self.OnForward(None)

    def OnPreviousTask(self, event):
        if self.timer.IsRunning():
            self.OnStop(event=None)
        self.OnBack(None)

    def _checkChangeTask(self):
        if self.timer.IsRunning():
            dlg = wx.MessageDialog(self, 'Stop currently running task before changing task',
                                   'Stop task',
                                   wx.OK | wx.ICON_WARNING)
            dlg.ShowModal()
            dlg.Destroy()
            return False
        return True

    def _loadConfiguration(self, event):

        def _includeTasks():
            tasks = []
            if "includeTasks" in self.configuration:
                folder = os.path.join(self._getTaskDir(), self.configuration['includeTasks'])
                if os.path.isdir(folder):
                    for file_ in [f for f in os.listdir(folder) if f.endswith('.json')]:
                        if file_ != os.path.basename(self.configFile):
                            with open(os.path.join(folder, file_), 'r') as f:
                                try:
                                    config = json.load(f)
                                except ValueError:
                                    wx.MessageBox(parent=self, message='Parsing error while reading %s.' % file_,
                                                  caption="Can't read JSON file", style=wx.OK | wx.ICON_ERROR)
                                    continue
                                tasks += config['tasks']
            return tasks

        self.configFile = self.configPath.GetValue().strip()
        if self.configFile:
            self.settings['activities']['config'] = self.configFile
            self._enableGUI(True)
            with open(self.configFile, 'r') as f:
                try:
                    self.configuration = json.load(f)
                    self.tasks = self.configuration['tasks']
                    self.tasks += _includeTasks()
                    self.title.SetLabel(self.tasks[self.current]['title'])
                    self.instructions.SetLabel(self._getInstructions())
                except ValueError:
                    self.configuration = {}
                    self.settings['activities']['config'] = ''
                    self._enableGUI(False)
                    wx.MessageBox(parent=self, message='Parsing error while reading JSON file, please correct it and try again.',
                                  caption="Can't read JSON file", style=wx.OK | wx.ICON_ERROR)
            self._bindUserStop()
        else:
            self.settings['activities']['config'] = ''
            self._enableGUI(False)

        self.slidesStatus.Show(bool('slides' in self.configuration and self.configuration['slides']))
        self.Layout()

    def _loadScanningParams(self, key):
        if key in self.tasks[self.current]:
            for each in self.tasks[self.current][key].keys():
                self.settings['scan'][each] = self.tasks[self.current][key][each]

    def Calibrate(self, startTask):
        self._loadConfiguration(None)
        if 'base' in self.tasks[self.current]:
            self.settings['scan']['elevation'] = self.tasks[self.current]['base']
        elif 'base_region' in self.tasks[self.current]:
            self.settings['scan']['region'] = self.tasks[self.current]['base_region']
        self.settings['output']['calibrate'] = True
        self.settings['analyses']['file'] = ''
        self._loadScanningParams(key='scanning_params')
        # just update whatever was not set with 'scanning_params'
        self._loadScanningParams(key='calibration_scanning_params')

        # resume scanning
        self.buttonCalibrate.SetLabel("Calibrating...")
        self.scaniface.filter['filter'] = False
        self._startScanning()

        wx.CallLater(2000, lambda: self.CalibrationDone(startTask))

    def CalibrationDone(self, startTask):
        def process():
            self.buttonCalibrate.SetLabel("Calibrate")
            self.settings['output']['calibrate'] = False
        self._stopScanning()
        wx.CallLater(4000, lambda: process())
        if startTask:
            wx.CallLater(4000, lambda: self.OnStart(None))

    def OnBack(self, event):
        if not self._checkChangeTask():
            return
        # check if possible to go back
        if self.current <= 0:
            # just for sure
            self.buttonBack.Enable(False)
            return
        # move back
        self.current -= 1
        if self.current <= 0:
            self.buttonBack.Enable(False)
        self.buttonForward.Enable(True)
        if self.tasks:
            self.title.SetLabel(self.tasks[self.current]['title'])
        self.timeText.SetLabel('00:00')
        self.buttonNext.Show('sublayers' in self.tasks[self.current])
        self.buttonCalibrate.Show('calibrate' in self.tasks[self.current] and self.tasks[self.current]['calibrate'])
        self.instructions.SetLabel(self._getInstructions())
        self.Layout()

    def OnForward(self, event):
        if not self._checkChangeTask():
            return
        # check if possible to go forward
        if self.current >= len(self.tasks) - 1:
            # just for sure
            self.buttonForward.Enable(False)
            return
        self.current += 1
        if self.current >= len(self.tasks) - 1:
            self.buttonForward.Enable(False)
        self.buttonBack.Enable(True)
        if self.tasks:
            self.title.SetLabel(self.tasks[self.current]['title'])
        self.timeText.SetLabel('00:00')
        self.buttonNext.Show('sublayers' in self.tasks[self.current])
        self.buttonCalibrate.Show('calibrate' in self.tasks[self.current] and self.tasks[self.current]['calibrate'])
        self.instructions.SetLabel(self._getInstructions())
        self.Layout()

    def StartAutomated(self, event):
        # Doesn't implement slides
        self._loadConfiguration(None)
        if 'calibrate' in self.tasks[self.current] and self.tasks[self.current]['calibrate']:
            self.Calibrate(startTask=True)
        else:
            self._startTask()

    def OnStart(self, event):
        self._loadConfiguration(None)
        if 'slides' in self.configuration and self.configuration['slides']:
            self._startSlides()
        else:
            # if no slides, start right away
            self._startTask()

    def _startSlides(self):
        # lazy import
        from activities_slides import Slides

        self.slides = Slides(self)
        self.slides.SetPosition(self.configuration['slides']['position'])
        self.slides.LoadURL('file://' + os.path.join(self.configuration['slides']['dir'], self.tasks[self.current]['slides']['file']))
        self.slides.Maximize(True)
        self.slides.Show()
        slidenum = 1
        self.slidesStatus.SetLabel("Slide {}".format(slidenum))
        for t in self.tasks[self.current]['slides']['switch']:
            slidenum += 1
            wx.CallLater(t * 1000, self._switchSlide, slidenum)
        wx.CallLater(self.tasks[self.current]['slides']['switch'][-1] * 1000, self._startTask)

    def _switchSlide(self, slidenum):
        if self.slides:  # in case it's closed prematurely
            self.slides.Next()
            self.slidesStatus.SetLabel("Slide {}".format(slidenum))

    def _getTaskDir(self):
        return self.configuration['taskDir'] if 'taskDir' in self.configuration else os.path.dirname(self.settings['activities']['config'])

    def _getInstructions(self):
        instr = self.configuration['tasks'][self.current]['instructions'] if 'instructions' in self.configuration['tasks'][self.current] else ''
        return wordwrap(instr, self.GetClientSize()[0] - 10, wx.ClientDC(self))

    def _hideToolbarStatusbar(self):
        """Hide toolbar and statusbar of active Map Display"""
        if self.IsStandalone():
            return
        self.giface.ShowAllToolbars(False)
        self.giface.ShowStatusbar(False)
        wx.CallLater(1000, self.giface.GetMapDisplay().PostSizeEvent)

    def _startTask(self):
        if self.timer.IsRunning():
            return

        self._hideToolbarStatusbar()
        self.currentSubtask = 0
        self._processingSubTask = False
        self.scaniface.additionalParams4Analyses = {'subTask': self.currentSubtask}
        self.LoadLayers()
        if 'base' in self.tasks[self.current]:
            self.settings['scan']['elevation'] = self.tasks[self.current]['base']
        elif 'base_region' in self.tasks[self.current]:
            self.settings['scan']['region'] = self.tasks[self.current]['base_region']
        self.settings['analyses']['file'] = os.path.join(self._getTaskDir(), self.tasks[self.current]['analyses'])
        self.settings['output']['scan'] = 'scan'
        self._loadScanningParams(key='scanning_params')

        # resume scanning
        if 'filter' in self.tasks[self.current]:
            self.scaniface.filter['filter'] = True
            self.scaniface.filter['counter'] = 0
            self.scaniface.filter['threshold'] = self.tasks[self.current]['filter']['threshold']
            self.scaniface.filter['debug'] = self.tasks[self.current]['filter']['debug']
        if 'single_scan' in self.tasks[self.current] and self.tasks[self.current]['single_scan']:
            self._stopScanning()
        else:
            self._startScanning()

        # profile
        if 'profile' in self.tasks[self.current]:
            self.StartProfile()
        # display
        if 'display' in self.tasks[self.current]:
            self.StartDisplay()

        wx.CallLater(1000, self._setFocus)

        self.startTime = datetime.datetime.now()
        self.endTime = 0
        self.timer.Start(100)

    def _setFocus(self):
        topParent = wx.GetTopLevelParent(self)
        topParent.Raise()
        topParent.SetFocus()

    def _closeAdditionalWindows(self):
        if self.slides:
            self.slides.Close()
            self.slidesStatus.SetLabel('Slides off')
        if self.profileFrame:
            self.profileFrame.Close()
            self.profileFrame = None
        if self.dashboardFrame:
            self.dashboardFrame.Destroy()
            self.dashboardFrame = None

    def _stopScanning(self):
        self.scaniface.pause = True
        self.scaniface.changedInput = True

    def _startScanning(self):
        self.scaniface.pause = False
        self.scaniface.changedInput = True

    def _removeAllLayers(self):
        ll = self.giface.GetLayerList()
        for l in reversed(ll):
            ll.DeleteLayer(l)

    def OnStop(self, event):
        self.timer.Stop()
        self._closeAdditionalWindows()
        self._removeAllLayers()
        self.settings['analyses']['file'] = ''
        if 'handsoff' in self.configuration:
            self.LoadHandsOff()
            # scan after hands off
            if 'duration_handsoff' in self.configuration:
                t = self.configuration['duration_handsoff']
            else:
                t = 1
            wx.CallLater(t, self._stop)
        else:
            self._stop()

    def _stop(self):
        # pause scanning
        self._stopScanning()
        if 'duration_handsoff_after' in self.configuration:
            t = self.configuration['duration_handsoff_after']
            wx.CallLater(t, self.PostProcessing)
        else:
            self.PostProcessing()
        self._setFocus()

    def OnTimer(self, event):
        diff = datetime.datetime.now() - self.startTime
        minutes = diff.seconds // 60
        seconds = diff.seconds - (minutes * 60)
        self.timeText.SetLabel('{:02d}:{:02d}'.format(minutes, seconds))
        self.endTime = diff.seconds
        if 'time_limit' in self.tasks[self.current] and \
           diff > datetime.timedelta(seconds=self.tasks[self.current]['time_limit']):
            self.timer.Stop()
            # sleep for several seconds now?
            self.OnStop(event=None)

    def LoadLayers(self):
        if self.IsStandalone():
            return
        ll = self.giface.GetLayerList()
        for i, cmd in enumerate(self.configuration['tasks'][self.current]['layers']):
            opacity = 1.0
            checked = True
            if "layers_opacity" in self.configuration['tasks'][self.current]:
                opacity_list = self.configuration['tasks'][self.current]['layers_opacity']
                if i < len(opacity_list):
                    opacity = float(opacity_list[i])
                else:
                    self.giface.WriteWarning("Number of layers is larger than the number of opacity values in config file")
            if "layers_checked" in self.configuration['tasks'][self.current]:
                checked_list = self.configuration['tasks'][self.current]['layers_checked']
                if i < len(checked_list):
                    checked = checked_list[i]
                else:
                    self.giface.WriteWarning("Number of layers is larger than the number of checked values in config file")
            if cmd[0] == 'd.rast':
                lr = ll.AddLayer('raster', name=cmd[1].split('=')[1], checked=checked,
                                 opacity=opacity, cmd=cmd)
            elif cmd[0] == 'd.vect':
                lr = ll.AddLayer('vector', name=cmd[1].split('=')[1], checked=checked,
                                 opacity=opacity, cmd=cmd)
            elif cmd[0] == 'd.labels':
                lr = ll.AddLayer('labels', name=cmd[1].split('=')[1], checked=checked,
                                 opacity=opacity, cmd=cmd)
            elif cmd[0] == 'd.shade':
                lr = ll.AddLayer('shaded', name=cmd[1].split('=')[1], checked=checked,
                                 opacity=opacity, cmd=cmd)
            elif cmd[0] == 'd.rgb':
                lr = ll.AddLayer('rgb', name=cmd[1].split('=')[1], checked=checked,
                                 opacity=opacity, cmd=cmd)
            elif cmd[0] == 'd.legend':
                lr = ll.AddLayer('rastleg', name=cmd[1].split('=')[1], checked=checked,
                                 opacity=opacity, cmd=cmd)
            elif cmd[0] == 'd.northarrow':
                lr = ll.AddLayer('northarrow', name=cmd[1].split('=')[1], checked=checked,
                                 opacity=opacity, cmd=cmd)
            elif cmd[0] == 'd.barscale':
                lr = ll.AddLayer('barscale', name=cmd[1].split('=')[1], checked=checked,
                                 opacity=opacity, cmd=cmd)
            else:
                lr = ll.AddLayer('command', name=' '.join(cmd), checked=checked,
                                 opacity=opacity, cmd=[])
            if not checked:
                # workaround: in not checked the order of layers is wrong
                try:
                    for each in ll:
                        ll.SelectLayer(each, False)
                    ll.SelectLayer(lr, True)
                except AttributeError:
                    # SelectLayer introduced in r73097, for cases before:
                    ll._tree.Unselect()
                    ll._tree.SelectItem(lr._layer, True)
        if 'sublayers' in self.tasks[self.current]:
            cmd = self.tasks[self.current]['sublayers'][0]
            if cmd[0] == 'd.rast':
                ll.AddLayer('raster', name=cmd[1].split('=')[1], checked=True,
                            opacity=1.0, cmd=cmd)
            elif cmd[0] == 'd.vect':
                ll.AddLayer('vector', name=cmd[1].split('=')[1], checked=True,
                            opacity=1.0, cmd=cmd)

        # zoom to base map
        self.ZoomToBase()

    def ZoomToBase(self):
        if self.IsStandalone():
            return
        if 'base' in self.configuration['tasks'][self.current]:
            base = self.configuration['tasks'][self.current]['base']
            self.giface.GetMapWindow().Map.GetRegion(rast=[base], update=True)
        elif 'base_region' in self.configuration['tasks'][self.current]:
            region = self.configuration['tasks'][self.current]['base_region']
            self.giface.GetMapWindow().Map.GetRegion(regionName=region, update=True)

        self.giface.GetMapWindow().UpdateMap()

    def LoadHandsOff(self):
        if self.IsStandalone():
            return
        ll = self.giface.GetLayerList()
        cmd = self.configuration['handsoff']
        self.handsoff = ll.AddLayer('command', name=' '.join(cmd), checked=True,
                                    opacity=1.0, cmd=[])

    def PostProcessing(self, onDone=None):
        wx.BeginBusyCursor()
        wx.SafeYield()
        env = get_environment(rast=self.settings['output']['scan'])  # noqa: F841
        try:
            postprocess = imp.load_source('postprocess', os.path.join(self._getTaskDir(), self.tasks[self.current]['analyses']))
        except Exception as e:
            print(e)
            return

        functions = [func for func in dir(postprocess) if func.startswith('post_')]
        for func in functions:
            exec('del postprocess.' + func)
        try:
            postprocess = imp.load_source('postprocess', os.path.join(self._getTaskDir(), self.tasks[self.current]['analyses']))
        except Exception as e:
            print(e)
            return
        functions = [func for func in dir(postprocess) if func.startswith('post_')]
        for func in functions:
            try:
                exec('postprocess.' + func + "(real_elev=self.settings['scan']['elevation'],"
                                             " scanned_elev=self.settings['output']['scan'],"
                                             " filterResults=self.scaniface.filter['counter'],"
                                             " timeToFinish=self.endTime,"
                                             " subTask=self.currentSubtask,"
                                             " logDir=self.configuration['logDir'],"
                                             " env=env)")
            except (CalledModuleError, Exception, ScriptError) as e:
                traceback.print_exc()
        wx.EndBusyCursor()
        if self.handsoff and not self.IsStandalone():
            ll = self.giface.GetLayerList()
            ll.DeleteLayer(self.handsoff)
            self.handsoff = None

        if onDone:
            onDone()

    def StartProfile(self):
        if not ProfileFrame:
            print('WARNING: DEM profile is not available, requires matplotlib library')
            return
        self.profileFrame = ProfileFrame(self)
        pos = self._getDashboardPosition(key='profile')
        size = self._getDashboardSize(key='profile')
        self.profileFrame.SetPosition(pos)
        self.profileFrame.SetSize(size)
        self.profileFrame.set_ticks(self.tasks[self.current]['profile']['ticks'])
        self.profileFrame.set_xlim(self.tasks[self.current]['profile']['limitx'])
        self.profileFrame.set_ylim(self.tasks[self.current]['profile']['limity'])
        self.profileFrame.Show()

    def OnProfileUpdate(self, event):
        # event can be received after frame is destroyed
        if not self.profileFrame:
            return
        env = get_environment(raster=self.tasks[self.current]['profile']['raster'])
        self.profileFrame.compute_profile(points=event.points, raster=self.tasks[self.current]['profile']['raster'], env=env)

    def StartDisplay(self):
        title = None if 'title' not in self.tasks[self.current]['display'] else self.tasks[self.current]['display']['title']
        vertical = False if 'vertical' not in self.tasks[self.current]['display'] else self.tasks[self.current]['display']['vertical']
        fontsize = self.tasks[self.current]['display']['fontsize']
        maximum = self.tasks[self.current]['display']['maximum']
        formatting_string = self.tasks[self.current]['display']['formatting_string']
        self.dashboardFrame = MultipleDashboardFrame(self, fontsize=fontsize, maximum=maximum,
                                                     title=title, formatting_string=formatting_string, vertical=vertical)

        pos = self._getDashboardPosition(key='display')
        size = self._getDashboardSize(key='display')
        self.dashboardFrame.SetSize(size)
        self.dashboardFrame.Show()
        self.dashboardFrame.SetPosition(pos)

    def _getDashboardPosition(self, key):
        if 'position' in self.tasks[self.current][key]:
            pos = self.tasks[self.current][key]['position']
        elif 'relative_position' in self.tasks[self.current][key]:
            relPos = self.tasks[self.current][key]['relative_position']
            pos = self._getPosFromRelative(relPos)
        else:
            pos = self._getPosFromRelative((1.01, 0.5))
        return pos

    def _getDashboardSize(self, key):
        if 'size' in self.tasks[self.current][key]:
            size = self.tasks[self.current][key]['size']
        elif 'relative_size' in self.tasks[self.current][key]:
            relSize = self.tasks[self.current][key]['relative_size']
            size = self._getSizeFromRelative(relSize)
        else:
            size = self._getSizeFromRelative((0.3, 0.3))
        return size

    def _getPosFromRelative(self, pos):
        if self.IsStandalone():
            md = wx.GetTopLevelParent(self)
        else:
            md = self.giface.GetMapDisplay()
        mdSize = md.GetSize()
        mdPos = md.GetPosition()
        return (mdPos[0] + pos[0] * mdSize[0], mdPos[1] + pos[1] * mdSize[1])

    def _getSizeFromRelative(self, size):
        if self.IsStandalone():
            md = wx.GetTopLevelParent(self)
        else:
            md = self.giface.GetMapDisplay()
        mdSize = md.GetSize()
        return (size[0] * mdSize[0], size[1] * mdSize[1])

    def OnDisplayUpdate(self, event):
        if not self.dashboardFrame:
            return
        self.dashboardFrame.show_value(event.value)

    def OnSubtask(self, event):
        self._processingSubTask = True
        self.LoadHandsOff()
        # keep scanning without hands
        if 'duration_handsoff' in self.configuration:
            t = self.configuration['duration_handsoff']
        else:
            t = 0
        wx.CallLater(t, self._subtaskStop)

    def _subtaskStop(self):
        # pause scanning
        self._stopScanning()
        if 'duration_handsoff_after' in self.configuration:
            t = self.configuration['duration_handsoff_after']
        else:
            t = 0
        if 'solutions' in self.tasks[self.current]:
            wx.CallLater(t, self.PostProcessing, onDone=self._showSolutions)
        else:
            wx.CallLater(t, self.PostProcessing, onDone=self._subtaskDone)

    def _showSolutions(self):
        if self.IsStandalone():
            return
        ll = self.giface.GetLayerList()
        if self.handsoff:
            ll.DeleteLayer(self.handsoff)

        cmd = self.tasks[self.current]['solutions'][self.currentSubtask]
        if cmd[0] == 'd.rast':
            ll.AddLayer('raster', name=cmd[1].split('=')[1], checked=True,
                        opacity=1.0, cmd=cmd)
        elif cmd[0] == 'd.vect':
            ll.AddLayer('vector', name=cmd[1].split('=')[1], checked=True,
                        opacity=1.0, cmd=cmd)
        wx.CallLater(6000, self._subtaskDone)

    def _subtaskDone(self):
        # check if it was the last subTask
        if self.currentSubtask + 1 >= len(self.tasks[self.current]['sublayers']):
            # that was the last one
            self.timer.Stop()
            self._closeAdditionalWindows()
            self._removeAllLayers()
            self.settings['analyses']['file'] = ''
        else:
            # load new layers
            ll = self.giface.GetLayerList()
            for l in ll:
                if 'solutions' in self.tasks[self.current] and l.cmd == self.tasks[self.current]["solutions"][self.currentSubtask]:
                    ll.DeleteLayer(l)
                    break
            ll = self.giface.GetLayerList()
            for l in ll:
                if l.cmd == self.tasks[self.current]["sublayers"][self.currentSubtask]:
                    ll.DeleteLayer(l)
                    cmd = self.tasks[self.current]["sublayers"][self.currentSubtask + 1]
                    if cmd[0] == 'd.rast':
                        ll.AddLayer('raster', name=cmd[1].split('=')[1], checked=True,
                                    opacity=1.0, cmd=cmd)
                    elif cmd[0] == 'd.vect':
                        ll.AddLayer('vector', name=cmd[1].split('=')[1], checked=True,
                                    opacity=1.0, cmd=cmd)
                    break
            self.currentSubtask += 1
            self.scaniface.additionalParams4Analyses = {'subTask': self.currentSubtask}
            # update
            self.scaniface.filter['counter'] = 0
            for each in self.giface.GetAllMapDisplays():
                each.GetMapWindow().UpdateMap()
            self._startScanning()

            self.Raise()
            self.buttonStop.SetFocus()
        # now user can proceed to next task
        self._processingSubTask = False

    def OnUserStop(self, event):
        if self._processingSubTask:
            return
        if 'sublayers' in self.tasks[self.current]:
            self.OnSubtask(None)
        else:
            self.OnStop(None)

    def OnScanOnce(self, event):
        self.scaniface.resume_once = True
        self.scaniface.changedInput = True

    def _reloadAnalysisFile(self, funcPrefix):
        analysesFile = os.path.join(self._getTaskDir(), self.configuration['tasks'][self.current]['analyses'])
        try:
            myanalyses = imp.load_source('myanalyses', analysesFile)
        except Exception:
            return None
        functions = [func for func in dir(myanalyses) if func.startswith(funcPrefix)]
        for func in functions:
            exec('del myanalyses.' + func)
        try:
            myanalyses = imp.load_source('myanalyses', analysesFile)
        except Exception:
            return None
        functions = [func for func in dir(myanalyses) if func.startswith(funcPrefix)]
        return myanalyses, functions
