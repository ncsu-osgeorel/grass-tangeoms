#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Nov 20 14:44:32 2013

@author: anna
"""

import os
import wx
import wx.lib.filebrowsebutton as filebrowse
from wx.adv import HyperlinkCtrl as UrlCtrl
from shutil import copyfile
from subprocess import PIPE, run
import signal
import tempfile

from grass.script.utils import set_path, get_lib_path
set_path(modulename='g.gui.tangible')
from grass.script.setup import set_gui_path
set_gui_path()

from gui_core.gselect import Select
from core.settings import UserSettings
import grass.script as gscript
from grass.pydispatch.signal import Signal
from grass.exceptions import CalledModuleError

from wxwrap import TextCtrl, Button, BitmapButton, SpinCtrl, CheckBox
from tangible_utils import get_environment, run_analyses, updateGUIEvt, get_TL_logo, EVT_UPDATE_GUI
from tangible_utils import EVT_ADD_LAYERS, EVT_REMOVE_LAYERS, EVT_CHECK_LAYERS, EVT_SELECT_LAYERS, EVT_CHANGE_LAYER
from drawing import DrawingPanel
from export import OutputPanel
from activities import ActivitiesPanel
from tangible_utils import get_show_layer_icon


class AboutPanel(wx.Panel):
    def __init__(self, parent, scaniface):
        wx.Panel.__init__(self, parent)
        scaniface = scaniface
        sensor = wx.StaticText(self, label="", style=wx.ALIGN_CENTRE_HORIZONTAL)
        if scaniface.sensor == 'k4a':
            sensor.SetLabel("Using Kinect Azure DK version of r.in.kinect")
        elif scaniface.sensor == 'k4w_v2':
            sensor.SetLabel("Using Kinect Xbox One version of r.in.kinect")
        elif sensor is None:
            sensor.SetLabel("WARNING: r.in.kinect not available")

        mainSizer = wx.BoxSizer(wx.VERTICAL)
        hbitmap = wx.StaticBitmap(self, wx.ID_ANY, get_TL_logo())
        name = wx.StaticText(self, label="Tangible Landscape plugin for GRASS GIS",
                             style=wx.ALIGN_CENTRE_HORIZONTAL)
        font = wx.Font(16, wx.DEFAULT, wx.NORMAL, wx.NORMAL)
        name.SetFont(font)
        url = UrlCtrl(self, label="tangible-landscape.github.io",
                      url="tangible-landscape.github.io")
        wiki = UrlCtrl(self, label="See documentation and tutorial on wiki",
                       url="github.com/tangible-landscape/grass-tangible-landscape/wiki")

        mainSizer.Add(hbitmap, proportion=0, flag=wx.EXPAND)
        mainSizer.Add(name, flag=wx.EXPAND)
        mainSizer.Add(url, flag=wx.EXPAND)
        mainSizer.AddStretchSpacer(1)
        mainSizer.Add(sensor, flag=wx.EXPAND)
        mainSizer.AddStretchSpacer(1)
        mainSizer.Add(wiki, flag=wx.EXPAND)
        mainSizer.AddStretchSpacer(1)

        self.SetSizer(mainSizer)
        mainSizer.Fit(self)


class AnalysesPanel(wx.Panel):
    def __init__(self, parent, giface, settings, scaniface):
        wx.Panel.__init__(self, parent)
        self.giface = giface
        self.settings = settings
        self.scaniface = scaniface
        self.settingsChanged = Signal('AnalysesPanel.settingsChanged')

        mainSizer = wx.BoxSizer(wx.VERTICAL)
        if self.settings['analyses']['file']:
            path = self.settings['analyses']['file']
            initDir = os.path.dirname(path)
        else:
            path = initDir = ""

        topoBox = wx.StaticBox(self, label='  Topographic analyses ')
        topoSizer = wx.StaticBoxSizer(topoBox, wx.VERTICAL)
        self.contoursSelect = Select(self, size=(-1, -1), type='vector')
        self.contoursStepTextCtrl = TextCtrl(self, size=(40, -1))
        self.contoursStepTextCtrl.SetToolTip("Contour step")

        if 'contours' in self.settings['analyses'] and self.settings['analyses']['contours']:
            self.contoursStepTextCtrl.SetValue(str(self.settings['analyses']['contours_step']))
            self.contoursSelect.SetValue(self.settings['analyses']['contours'])

        bmp = get_show_layer_icon()
        self.addContours = wx.BitmapButton(self, bitmap=bmp, size=(bmp.GetWidth() + 12, bmp.GetHeight() + 8))
        self.addContours.Bind(wx.EVT_BUTTON, self._addContourLayer)

        self.contoursSelect.Bind(wx.EVT_TEXT, self.OnAnalysesChange)
        self.contoursStepTextCtrl.Bind(wx.EVT_TEXT, self.OnAnalysesChange)

        fileBox = wx.StaticBox(self, label='  Python file with analyses to run ')
        fileSizer = wx.StaticBoxSizer(fileBox, wx.VERTICAL)
        self.selectAnalyses = filebrowse.FileBrowseButton(self, labelText="File path:", fileMask="Python file (*.py)|*.py",
                                                          startDirectory=initDir, initialValue=path,
                                                          changeCallback=lambda evt: self.SetAnalysesFile(evt.GetString()))
        if self.settings['analyses']['file']:
            self.selectAnalyses.SetValue(self.settings['analyses']['file'])

        newAnalyses = wx.Button(self, label="Create new file with predefined analyses")
        newAnalyses.Bind(wx.EVT_BUTTON, lambda evt: self.CreateNewFile())
        self.selectAnalyses.Bind(wx.EVT_TEXT, self.OnAnalysesChange)

        if 'color_training' not in self.settings['analyses']:
            self.settings['analyses']['color_training'] = ''

        colorBox = wx.StaticBox(self, label='  Color calibration for classification  ')
        colorSizer = wx.StaticBoxSizer(colorBox, wx.VERTICAL)
        self.trainingAreas = Select(self, size=(-1, -1), type='raster')
        self.trainingAreas.SetValue(self.settings['analyses']['color_training'])
        self.trainingAreas.Bind(wx.EVT_TEXT, self.OnAnalysesChange)
        calibrateBtn = wx.Button(self, label="Calibrate")
        calibrateBtn.Bind(wx.EVT_BUTTON, self.OnColorCalibration)

        bmp = get_show_layer_icon()
        addLayerBtn = BitmapButton(self, bitmap=bmp, size=(bmp.GetWidth() + 12, bmp.GetHeight() + 8))
        addLayerBtn.SetToolTip("Add layer to display")
        addLayerBtn.Bind(wx.EVT_BUTTON, self._addCalibLayer)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(wx.StaticText(self, label="Contour map name:"), proportion=0, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=5)
        sizer.Add(self.contoursSelect, proportion=4, flag=wx.ALIGN_CENTER_VERTICAL, border=5)
        sizer.Add(self.addContours, proportion=0, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=5)
        sizer.Add(wx.StaticText(self, label="Interval:"), proportion=0, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=5)
        sizer.Add(self.contoursStepTextCtrl, proportion=1, flag=wx.ALIGN_CENTER_VERTICAL, border=5)
        topoSizer.Add(sizer, flag=wx.EXPAND | wx.ALL, border=5)
        mainSizer.Add(topoSizer, flag=wx.EXPAND | wx.ALL, border=5)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.selectAnalyses, proportion=1, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=5)
        fileSizer.Add(sizer, flag=wx.EXPAND | wx.ALL, border=5)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.AddStretchSpacer()
        sizer.Add(newAnalyses, proportion=1, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=5)
        fileSizer.Add(sizer, flag=wx.EXPAND | wx.ALL, border=5)
        mainSizer.Add(fileSizer, flag=wx.EXPAND | wx.ALL, border=5)

        # color training
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(wx.StaticText(self, label="Raster with training areas:"), proportion=0, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=5)
        sizer.Add(self.trainingAreas, proportion=1, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=1)
        sizer.Add(addLayerBtn, proportion=0, flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=5)
        sizer.Add(calibrateBtn, proportion=0, flag=wx.ALIGN_CENTER_VERTICAL)
        colorSizer.Add(sizer, flag=wx.EXPAND | wx.ALL, border=5)
        mainSizer.Add(colorSizer, flag=wx.EXPAND | wx.ALL, border=5)

        self.SetSizer(mainSizer)
        mainSizer.Fit(self)

    def SetAnalysesFile(self, path):
        self.settings['analyses']['file'] = path

    def OnAnalysesChange(self, event):
        self.settings['analyses']['contours'] = self.contoursSelect.GetValue()
        self.settings['analyses']['contours_step'] = self.contoursStepTextCtrl.GetValue()
        self.settings['analyses']['file'] = self.selectAnalyses.GetValue()
        self.settings['analyses']['color_training'] = self.trainingAreas.GetValue()
        self.settingsChanged.emit()

    def CreateNewFile(self):
        get_lib_path('g.gui.tangible')
        dlg = wx.FileDialog(self, message="Create a new file with analyses",
                            wildcard="Python source (*.py)|*.py",
                            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            orig = os.path.join(get_lib_path('g.gui.tangible'), 'current_analyses.py')
            if not os.path.exists(orig):
                self.giface.WriteError("File with analyses not found: {}".format(orig))
            else:
                copyfile(orig, path)
                self.selectAnalyses.SetValue(path)
                self.settings['analyses']['file'] = path
        dlg.Destroy()

    def OnColorCalibration(self, event):
        if self.scaniface.IsScanning():
            dlg = wx.MessageDialog(self, 'In order to calibrate, please stop scanning process first.',
                                   'Stop scanning',
                                   wx.OK | wx.ICON_WARNING)
            dlg.ShowModal()
            dlg.Destroy()
            return

        training = self.trainingAreas.GetValue()
        if not training:
            return
        if self.settings['output']['color'] and self.settings['output']['color_name']:
            self.group = self.settings['output']['color_name']
        else:
            self.group = None
            dlg = wx.MessageDialog(self, "In order to calibrate colors, please specify name of output color raster in 'Output' tab.",
                                   'Need color output',
                                   wx.OK | wx.ICON_WARNING)
            dlg.ShowModal()
            dlg.Destroy()
            return

        self.CalibrateColor()

    def CalibrateColor(self):
        ll = self.giface.GetLayerList()
        checked = []
        for l in ll:
            if ll.IsLayerChecked(l):
                checked.append(l.cmd)
                ll.CheckLayer(l, False)
        wx.Yield()

        self.scaniface.Scan(continuous=False)
        self.scaniface.process.communicate()
        self.scaniface.process = None
        self.scaniface.status.SetLabel("Done.")

        self._defineEnvironment()

        self._calibrateColor()
        # check the layers back to previous state
        ll = self.giface.GetLayerList()
        for l in ll:
            if l.cmd in checked:
                ll.CheckLayer(l, True)

    def _calibrateColor(self):
        gscript.run_command('i.gensigset', trainingmap=self.settings['analyses']['color_training'], group=self.group,
                            subgroup=self.group, signaturefile='signature', env=self.env, overwrite=True)  # we need here overwrite=True

    def _defineEnvironment(self):
        self.env = None
        maps = gscript.read_command('i.group', flags='g', group=self.group, subgroup=self.group, quiet=True).strip()
        if maps:
            self.env = get_environment(raster=maps.splitlines()[0])

    def _addCalibLayer(self, event):
        if not self.giface.GetLayerTree():
            return
        ll = self.giface.GetLayerList()
        raster = self.trainingAreas.GetValue()
        if not raster:
            return
        cmd = ['d.rast', 'map=' + raster]
        ll.AddLayer('raster', name=raster, checked=True, cmd=cmd)

    def _addContourLayer(self, event):
        ll = self.giface.GetLayerList()
        if not self.giface.GetLayerTree():
            return
        vector = self.contoursSelect.GetValue()
        if not vector:
            return
        cmd = ['d.vect', 'map=' + vector]
        ll.AddLayer('vector', name=vector, checked=True, cmd=cmd)


class ScanningPanel(wx.Panel):
    def __init__(self, parent, giface, settings, scaniface):
        wx.Panel.__init__(self, parent)
        self.giface = giface
        self.settings = settings
        self.scaniface = scaniface
        if 'scan' not in self.settings:
            self.settings['scan'] = {}
            self.settings['scan']['elevation'] = ''
            self.settings['scan']['region'] = ''
            self.settings['scan']['zexag'] = 1
            self.settings['scan']['smooth'] = 8
            self.settings['scan']['numscans'] = 1
            self.settings['scan']['rotation_angle'] = 180
            self.settings['scan']['resolution'] = 2
            self.settings['scan']['trim_nsewtb'] = '30,30,30,30,50,150'
            self.settings['scan']['interpolate'] = False
            self.settings['scan']['trim_tolerance'] = ''
            self.settings['scan']['resolution'] = 2
            if self.scaniface.sensor == 'k4a':
                self.settings['scan']['color_resolution'] = ''
                self.settings['scan']['camera_resolution'] = '720P'

        self.scan = self.settings['scan']

        self.settingsChanged = Signal('ScanningPanel.settingsChanged')

        mainSizer = wx.BoxSizer(wx.VERTICAL)
        # define static boxes before all widgets are defined
        geomBox = wx.StaticBox(self, label='  Scan geometry  ')
        geomSizer = wx.StaticBoxSizer(geomBox, wx.VERTICAL)
        demBox = wx.StaticBox(self, label=' DEM quality ')
        demSizer = wx.StaticBoxSizer(demBox, wx.VERTICAL)
        georefBox = wx.StaticBox(self, label='  Georeferencing  ')
        if self.scaniface.sensor == 'k4a':
            colorBox = wx.StaticBox(self, label=' Color quality ')
            colorSizer = wx.StaticBoxSizer(colorBox, wx.VERTICAL)
            georefSizer = wx.StaticBoxSizer(georefBox, wx.HORIZONTAL)
        else:
            georefSizer = wx.StaticBoxSizer(georefBox, wx.VERTICAL)

        # create widgets
        self.btnCalibrateTilt = Button(self, label="Calibration 1")
        self.btnCalibrateTilt.SetToolTip('Calibrate to remove tilt of the scanner and to set suitable distance from the scanner')
        self.btnCalibrateExtent = Button(self, label="Calibration 2")
        self.btnCalibrateExtent.SetToolTip('Calibrate to identify the extent and position of the scanned object')

        # widgets for model
        self.elevInput = Select(self, size=(-1, -1), type='raster')
        self.elevInput.SetToolTip('Raster from which we take the georeferencing information')
        self.regionInput = Select(self, size=(-1, -1), type='region')
        self.regionInput.SetToolTip('Saved region from which we take the georeferencing information')
        self.zexag = TextCtrl(self)
        self.zexag.SetMinSize((50, -1))
        self.zexag.SetToolTip('Set vertical exaggeration of the physical model')
        self.numscans = SpinCtrl(self, min=1, max=5, initial=1)
        self.numscans.SetToolTip('Set number of scans to integrate')
        self.rotate = SpinCtrl(self, min=0, max=360, initial=180)
        self.rotate.SetToolTip('Set angle of rotation of the sensor around Z axis (typically 180 degrees)')
        self.smooth = TextCtrl(self)
        self.smooth.SetToolTip('Set smoothing of the DEM (typically between 7 to 12, higher value means more smoothing)')
        self.resolution = TextCtrl(self)
        self.resolution.SetToolTip('Raster resolution in mm of the ungeoreferenced scan')
        self.trim = {}
        for each in 'tbnsew':
            self.trim[each] = TextCtrl(self, size=(40, -1))
            if each in 'tb':
                self.trim[each].SetToolTip('Distance from the scanner')
            else:
                self.trim[each].SetToolTip('Distance from the center of scanning to the scanning boundary')
        self.trim_tolerance = TextCtrl(self)
        self.trim_tolerance.SetToolTip('Automatic trimming of the edges for rectangular models')
        self.interpolate = CheckBox(self, label="Use interpolation instead of binning")
        self.interpolate.SetToolTip('Interpolation avoids gaps in the scan, but takes longer')

        self.elevInput.SetValue(self.scan['elevation'])
        self.regionInput.SetValue(self.scan['region'])
        self.zexag.SetValue(str(self.scan['zexag']))
        self.rotate.SetValue(self.scan['rotation_angle'])
        self.numscans.SetValue(self.scan['numscans'])
        self.interpolate.SetValue(self.scan['interpolate'])
        for i, each in enumerate('nsewtb'):
            self.trim[each].SetValue(self.scan['trim_nsewtb'].split(',')[i])
        self.smooth.SetValue(str(self.scan['smooth']))
        self.resolution.SetValue(str(self.scan['resolution']))
        self.trim_tolerance.SetValue(str(self.scan['trim_tolerance']))
        if self.scaniface.sensor == 'k4a':
            self.cameraResolution = wx.Choice(self, choices=['depth', '720P', '1080P', '1440P', '2160P'])
            self.cameraResolution.SetToolTip("Applicable only when outputting color raster.\n"
                                             "Higher resolution results in longer processing.\n"
                                             "Set color resolution to lower value to take advantage of higher resolution.")
            self.cameraResolution.SetStringSelection(self.scan.get('camera_resolution', '720P'))
            self.colorResolution = TextCtrl(self)
            self.colorResolution.SetToolTip("Raster resolution of color output in mm of the ungeoreferenced scan")
            self.colorResolution.SetValue(str(self.scan.get('color_resolution', '')))

        # layout
        #
        # Geometry box
        #
        # rotation
        hSizer = wx.BoxSizer(wx.HORIZONTAL)
        hSizer.Add(wx.StaticText(self, label="Rotation angle:"), proportion=1, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=5)
        hSizer.Add(self.rotate, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=5)
        geomSizer.Add(hSizer, flag=wx.EXPAND)
        # trimming
        hSizer = wx.BoxSizer(wx.HORIZONTAL)
        hSizer.Add(wx.StaticText(self, label="Trim vertically [cm]:"), proportion=1, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=5)
        for each in 'tb':
            hSizer.Add(wx.StaticText(self, label=each.upper() + ':'), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=2)
            hSizer.Add(self.trim[each], flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=2)
        hSizer.Add(self.btnCalibrateTilt, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=2)
        geomSizer.Add(hSizer, flag=wx.EXPAND)
        hSizer = wx.BoxSizer(wx.HORIZONTAL)
        hSizer.Add(wx.StaticText(self, label="Trim horizontally [cm]:"), proportion=1, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=5)
        for each in 'nsew':
            hSizer.Add(wx.StaticText(self, label=each.upper() + ':'), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=3)
            hSizer.Add(self.trim[each], flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=2)
        hSizer.Add(self.btnCalibrateExtent, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=2)
        geomSizer.Add(hSizer, flag=wx.EXPAND)
        # automatic trim
        hSizer = wx.BoxSizer(wx.HORIZONTAL)
        hSizer.Add(wx.StaticText(self, label="Trim tolerance [0-1]:"), proportion=1, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=5)
        hSizer.Add(self.trim_tolerance, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=5)
        geomSizer.Add(hSizer, flag=wx.EXPAND)
        mainSizer.Add(geomSizer, flag=wx.EXPAND | wx.ALL, border=10)

        hSizer2 = wx.BoxSizer(wx.HORIZONTAL)
        if self.scaniface.sensor != 'k4a':
            #
            # Georeferencing box
            #
            # model parameters
            hSizer = wx.BoxSizer(wx.HORIZONTAL)
            hSizer.Add(wx.StaticText(self, label="Reference DEM:"), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=5)
            hSizer.Add(self.elevInput, proportion=1, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=5)
            georefSizer.Add(hSizer, flag=wx.EXPAND)
            # region
            hSizer = wx.BoxSizer(wx.HORIZONTAL)
            hSizer.Add(wx.StaticText(self, label="Reference region:"), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=5)
            hSizer.Add(self.regionInput, proportion=1, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=5)
            georefSizer.Add(hSizer, flag=wx.EXPAND)
            hSizer = wx.BoxSizer(wx.HORIZONTAL)
            hSizer.Add(wx.StaticText(self, label="Z-exaggeration:"), proportion=1, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=5)
            hSizer.Add(self.zexag, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=5)
            georefSizer.Add(hSizer, flag=wx.EXPAND)
            hSizer2.Add(georefSizer, proportion=1, flag=wx.EXPAND | wx.RIGHT, border=10)
        #
        # DEM properties box
        #
        # number of scans
        hSizer = wx.BoxSizer(wx.HORIZONTAL)
        hSizer.Add(wx.StaticText(self, label="Number of scans:"), proportion=1, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=5)
        hSizer.Add(self.numscans, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=5)
        demSizer.Add(hSizer, flag=wx.EXPAND)

        # smooth
        hSizer = wx.BoxSizer(wx.HORIZONTAL)
        hSizer.Add(wx.StaticText(self, label="Smooth value:"), proportion=1, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=5)
        hSizer.Add(self.smooth, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=5)
        demSizer.Add(hSizer, flag=wx.EXPAND)
        # resolution
        hSizer = wx.BoxSizer(wx.HORIZONTAL)
        hSizer.Add(wx.StaticText(self, label="Resolution [mm]:"), proportion=1, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=5)
        hSizer.Add(self.resolution, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=5)
        demSizer.Add(hSizer, flag=wx.EXPAND)

        hSizer = wx.BoxSizer(wx.HORIZONTAL)
        hSizer.Add(self.interpolate, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=5)
        demSizer.Add(hSizer, flag=wx.EXPAND)

        hSizer2.Add(demSizer, proportion=1, flag=wx.EXPAND | wx.RIGHT, border=10)

        # Color properties box
        if self.scaniface.sensor == 'k4a':
            hSizer = wx.BoxSizer(wx.HORIZONTAL)
            hSizer.Add(wx.StaticText(self, label="RGB camera resolution:"), flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=5)
            hSizer.Add(self.cameraResolution, proportion=1, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=5)
            colorSizer.Add(hSizer, flag=wx.EXPAND)

            hSizer = wx.BoxSizer(wx.HORIZONTAL)
            hSizer.Add(wx.StaticText(self, label="Resolution [mm]:"), proportion=1, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=5)
            hSizer.Add(self.colorResolution, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL, border=5)
            colorSizer.Add(hSizer, flag=wx.EXPAND)

            hSizer2.Add(colorSizer, proportion=1, flag=wx.EXPAND)
        mainSizer.Add(hSizer2, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=10)

        if self.scaniface.sensor == 'k4a':
            #
            # Georeferencing box
            #
            # model parameters
            hSizer = wx.BoxSizer(wx.HORIZONTAL)
            hSizer.Add(wx.StaticText(self, label="Reference DEM:"), proportion=0, flag=wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, border=5)
            hSizer.Add(self.elevInput, proportion=1, flag=wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, border=5)
            # region
            hSizer.Add(wx.StaticText(self, label="or region:"), proportion=0, flag=wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, border=5)
            hSizer.Add(self.regionInput, proportion=1, flag=wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, border=5)

            hSizer.Add(wx.StaticText(self, label="Z-exaggeration:"), proportion=0, flag=wx.RIGHT | wx.ALIGN_CENTER_VERTICAL, border=5)
            hSizer.Add(self.zexag, proportion=0, flag=wx.ALIGN_CENTER_VERTICAL, border=5)
            georefSizer.Add(hSizer, proportion=1, flag=wx.EXPAND | wx.ALL, border=5)
            mainSizer.Add(georefSizer, flag=wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, border=10)

        self.SetSizer(mainSizer)
        mainSizer.Fit(self)

        self.BindModelProperties()

    def BindModelProperties(self):
        self.btnCalibrateTilt.Bind(wx.EVT_BUTTON, self.scaniface.Calibrate)
        self.btnCalibrateExtent.Bind(wx.EVT_BUTTON, self.scaniface.CalibrateModelBBox)

        # model parameters
        self.elevInput.Bind(wx.EVT_TEXT, self.OnModelProperties)
        self.regionInput.Bind(wx.EVT_TEXT, self.OnModelProperties)
        self.zexag.Bind(wx.EVT_TEXT, self.OnModelProperties)
        self.rotate.Bind(wx.EVT_SPINCTRL, self.OnModelProperties)
        self.rotate.Bind(wx.EVT_TEXT, self.OnModelProperties)
        self.numscans.Bind(wx.EVT_SPINCTRL, self.OnModelProperties)
        self.numscans.Bind(wx.EVT_TEXT, self.OnModelProperties)
        self.interpolate.Bind(wx.EVT_CHECKBOX, self.OnModelProperties)
        self.smooth.Bind(wx.EVT_TEXT, self.OnModelProperties)
        self.resolution.Bind(wx.EVT_TEXT, self.OnModelProperties)
        self.trim_tolerance.Bind(wx.EVT_TEXT, self.OnModelProperties)
        for each in 'nsewtb':
            self.trim[each].Bind(wx.EVT_TEXT, self.OnModelProperties)
        if self.scaniface.sensor == 'k4a':
            self.cameraResolution.Bind(wx.EVT_CHOICE, self.OnModelProperties)
            self.colorResolution.Bind(wx.EVT_TEXT, self.OnModelProperties)

    def OnModelProperties(self, event):
        self.scan['elevation'] = self.elevInput.GetValue()
        self.scan['region'] = self.regionInput.GetValue()
        self.scan['rotation_angle'] = self.rotate.GetValue()
        self.scan['numscans'] = self.numscans.GetValue()
        self.scan['interpolate'] = self.interpolate.IsChecked()
        self.scan['smooth'] = self.smooth.GetValue()
        self.scan['resolution'] = self.resolution.GetValue()
        trim_tol = self.trim_tolerance.GetValue()
        self.scan['trim_tolerance'] = float(trim_tol) if trim_tol else trim_tol

        try:
            self.scan['zexag'] = float(self.zexag.GetValue())
            nsewtb_list = []
            for each in 'nsewtb':
                nsewtb_list.append(self.trim[each].GetValue())
            self.scan['trim_nsewtb'] = ','.join(nsewtb_list)
        except ValueError:
            pass
        if self.scaniface.sensor == 'k4a':
            self.scan['color_resolution'] = self.colorResolution.GetValue()
            self.scan['camera_resolution'] = self.cameraResolution.GetStringSelection()

        self.settingsChanged.emit()


class TangibleLandscapePlugin(wx.Dialog):
    def __init__(self, giface, parent):
        wx.Dialog.__init__(self, parent, title="Tangible Landscape", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.giface = giface
        self.parent = parent

        if not gscript.find_program('r.in.kinect'):
            self.giface.WriteError("ERROR: Module r.in.kinect not found.")
            self.sensor = None
        else:
            self.sensor = self.getSensorVersion()

        if not self.giface.GetLayerTree():
            self.giface.WriteWarning(("Running in standalone mode with "
                                      "limited functionality.\n"
                                      "You may want to launch g.gui.tangible from "
                                      "GRASS GUI console instead."))
        # Try killing r.in.kinect for recovery
        self.killKinect()
        self.settings = {}
        UserSettings.ReadSettingsFile(settings=self.settings)
        # for the first time
        if 'tangible' not in self.settings:
            self.settings['tangible'] = {'calibration': {'matrix': None},
                                         'analyses': {'file': None,
                                                      'contours': None,
                                                      'contours_step': 1}
                                         }
        self.calib_matrix = self.settings['tangible']['calibration']['matrix']

        self.delay = 0.3
        self.process = None
        self.observer = None
        self.signal_file = None
        self.timer = wx.Timer(self)
        self.changedInput = False
        self.filter = {'filter': False,
                       'counter': 0,
                       'threshold': 0.1,
                       'debug': False}
        # to be able to add params to runAnalyses from outside
        self.additionalParams4Analyses = {}

        self.notebook = wx.Notebook(self)
        self.scanning_panel = ScanningPanel(self.notebook, self.giface, self.settings['tangible'], scaniface=self)
        self.notebook.AddPage(self.scanning_panel, "Scanning")
        self.scan = self.settings['tangible']['scan']

        self.outputPanel = OutputPanel(self.notebook, self.giface, self.settings['tangible'])
        self.notebook.AddPage(self.outputPanel, "Output")
        self.scanning_panel.settingsChanged.connect(lambda: setattr(self, 'changedInput', True))
        analyses_panel = AnalysesPanel(self.notebook, self.giface, self.settings['tangible'], scaniface=self)
        self.notebook.AddPage(analyses_panel, "Analyses")
        analyses_panel.settingsChanged.connect(lambda: setattr(self, 'changedInput', True))
        self.outputPanel.settingsChanged.connect(lambda: setattr(self, 'changedInput', True))
        self.drawing_panel = DrawingPanel(self.notebook, self.giface, self.settings['tangible'])
        self.notebook.AddPage(self.drawing_panel, "Drawing")
        self.drawing_panel.Bind(EVT_UPDATE_GUI, self.OnUpdate)
        self.drawing_panel.settingsChanged.connect(lambda: setattr(self, 'changedInput', True))
        self.activities_panel = ActivitiesPanel(self.notebook, self.giface, self.settings['tangible'], scaniface=self)
        self.notebook.AddPage(self.activities_panel, "Activities")
        self.about_panel = AboutPanel(self.notebook, scaniface=self)
        self.notebook.AddPage(self.about_panel, "About")

        btnStart = wx.Button(self, label="Start")
        btnStop = wx.Button(self, label="Stop")
        btnPause = wx.Button(self, label="Pause")
        self.btnPause = btnPause
        btnScanOnce = wx.Button(self, label="Scan once")
        btnHelp = wx.Button(self, label="Help")
        btnClose = wx.Button(self, label="Close")
        self.status = wx.StaticText(self)

        # bind events
        btnStart.Bind(wx.EVT_BUTTON, lambda evt: self.Start())
        btnStop.Bind(wx.EVT_BUTTON, lambda evt: self.Stop())
        btnPause.Bind(wx.EVT_BUTTON, lambda evt: self.Pause())
        btnScanOnce.Bind(wx.EVT_BUTTON, self.ScanOnce)
        btnHelp.Bind(wx.EVT_BUTTON, self.OnHelp)
        btnClose.Bind(wx.EVT_BUTTON, self.OnClose)
        self.Layout()

        sizer = wx.BoxSizer(wx.VERTICAL)
        hSizer = wx.BoxSizer(wx.HORIZONTAL)
        hSizer.Add(btnStart, flag=wx.EXPAND | wx.ALL, border=5)
        hSizer.Add(btnStop, flag=wx.EXPAND | wx.ALL, border=5)
        hSizer.Add(btnPause, flag=wx.EXPAND | wx.ALL, border=5)
        hSizer.Add(btnScanOnce, flag=wx.EXPAND | wx.ALL, border=5)
        sizer.Add(hSizer, 0, wx.ALL | wx.EXPAND, 5)
        hSizer = wx.BoxSizer(wx.HORIZONTAL)
        hSizer.Add(self.status, flag=wx.EXPAND | wx.LEFT, border=5)
        sizer.Add(hSizer)
        sizer.Add(self.notebook, 1, wx.ALL | wx.EXPAND, 5)
        hSizer = wx.BoxSizer(wx.HORIZONTAL)
        hSizer.AddStretchSpacer()
        hSizer.Add(btnHelp, flag=wx.EXPAND | wx.ALL, border=5)
        hSizer.Add(btnClose, flag=wx.EXPAND | wx.ALL, border=5)
        sizer.Add(hSizer, flag=wx.EXPAND)

        self.SetSizer(sizer)
        sizer.Fit(self)
        self.SetMinSize(self.GetBestSize())
        self.Layout()

        self.Bind(wx.EVT_TIMER, self.RestartIfNotRunning, self.timer)
        self.Bind(wx.EVT_CLOSE, self.OnClose)
        self.Bind(EVT_UPDATE_GUI, self.OnUpdate)
        self.Bind(EVT_ADD_LAYERS, self.OnAddLayers)
        self.Bind(EVT_REMOVE_LAYERS, self.OnRemoveLayers)
        self.Bind(EVT_CHECK_LAYERS, self.OnCheckLayers)
        self.Bind(EVT_SELECT_LAYERS, self.OnSelectLayers)
        self.Bind(EVT_CHANGE_LAYER, self.OnChangeLayer)

        self.pause = None
        self.resume_once = None

        wx.CallAfter(self._refreshPanelSizes)

    def _refreshPanelSizes(self):
        """Workaround weird not updating page layout"""
        count = self.notebook.GetPageCount()
        for c in range(count):
            size = self.notebook.GetPage(c).GetSize()
            self.notebook.GetPage(c).SetSize(size)

    def getSensorVersion(self):
        nuldev = open(os.devnull, 'w+')
        try:
            out = gscript.read_command('r.in.kinect', flags='i', stderr=nuldev)
            version = out.strip().split('=')[-1]
        except CalledModuleError:
            version = 'k4w_v2'
        nuldev.close()
        return version

    def _getSignalFile(self):
        if not self.signal_file:
            fd, self.signal_file = tempfile.mkstemp()
            os.close(fd)
        return self.signal_file

    def killKinect(self):
        if run(['pkill', 'r.in.kinect']).returncode == 0:
            gscript.warning("Abandoned r.in.kinect process has been cleaned up.")

    def OnHelp(self, event):
        """Show help"""
        self.giface.Help(entry='g.gui.tangible', online=False)

    def OnClose(self, event):
        self.Stop()
        UserSettings.SaveToFile(self.settings)
        if self.signal_file and os.path.exists(self.signal_file):
            os.remove(self.signal_file)
        self.Destroy()

    def OnUpdate(self, event=None):
        for each in self.giface.GetAllMapDisplays():
            each.GetMapWindow().UpdateMap(delay=self.delay)

    def CalibrateModelBBox(self, event):
        if self.IsScanning():
            dlg = wx.MessageDialog(self, 'In order to calibrate, please stop scanning process first.',
                                   'Stop scanning',
                                   wx.OK | wx.ICON_WARNING)
            dlg.ShowModal()
            dlg.Destroy()
            return
        params = {}
        if self.calib_matrix:
            params['calib_matrix'] = self.calib_matrix
        params['rotate'] = self.scan['rotation_angle']
        zrange = ','.join(self.scan['trim_nsewtb'].split(',')[4:])
        params['zrange'] = zrange
        res = gscript.parse_command('r.in.kinect', flags='m', overwrite=True, **params)
        if not res['bbox']:
            gscript.message(_("Failed to find model extent"))
        offsetcm = 2
        n, s, e, w = [int(round(float(each))) for each in res['bbox'].split(',')]
        self.scanning_panel.trim['n'].SetValue(str(n + offsetcm))
        self.scanning_panel.trim['s'].SetValue(str(abs(s) + offsetcm))
        self.scanning_panel.trim['e'].SetValue(str(e + offsetcm))
        self.scanning_panel.trim['w'].SetValue(str(abs(w) + offsetcm))

    def Calibrate(self, event):
        if self.IsScanning():
            dlg = wx.MessageDialog(self, 'In order to calibrate, please stop scanning process first.',
                                   'Stop scanning',
                                   wx.OK | wx.ICON_WARNING)
            dlg.ShowModal()
            dlg.Destroy()
            return
        dlg = wx.MessageDialog(self, 'In order to calibrate, please remove objects from the table.',
                               'Calibration',
                               wx.OK | wx.CANCEL | wx.ICON_INFORMATION)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        dlg.Destroy()

        res = gscript.parse_command('r.in.kinect', flags='c', overwrite=True)
        if not (res['calib_matrix'] and len(res['calib_matrix'].split(',')) == 9):
            gscript.message(_("Failed to calibrate"))
            return
        else:
            self.giface.WriteCmdLog("Measured and corrected tilting of sensor: {angle} degrees".format(angle=res['angle_deviation']))
            if float(res['angle_deviation']) > 3:
                self.giface.WriteWarning("Angle deviation is too high, please level the sensor.")

        offsetcm = 1
        height = str(round(float(res['height']) * 100 - offsetcm, 1))
        self.scanning_panel.trim['b'].SetValue(height)
        nswetb = self.settings['tangible']['scan']['trim_nsewtb'].split(',')
        nswetb[-1] = height
        self.settings['tangible']['scan']['trim_nsewtb'] = ','.join(nswetb)
        self.settings['tangible']['calibration']['matrix'] = res['calib_matrix']
        UserSettings.SaveToFile(self.settings)

        # update
        self.calib_matrix = res['calib_matrix']

    def GatherParameters(self, editMode, continuous):
        """Create dict of input parameteres for r.in.kinect.
        Parameter editMode=True is needed when this dict is passed as stdin
        into r.in.kinect during scanning. Parameter continuous is needed when
        the scanning is supposed to run in loop and not just once"""
        params = {}
        if self.settings['tangible']['output']['calibrate'] and \
            self.settings['tangible']['output']['calibration_scan']:
            params['output'] = self.settings['tangible']['output']['calibration_scan'] + 'tmp'
        elif self.settings['tangible']['output']['scan']:
            params['output'] = self.settings['tangible']['output']['scan'] + 'tmp'
        # drawing
        if self.settings['tangible']['drawing']['active'] and self.settings['tangible']['drawing']['name']:
            params['draw_output'] = self.settings['tangible']['drawing']['name']
            params['draw'] = self.settings['tangible']['drawing']['type']
            params['draw_threshold'] = self.settings['tangible']['drawing']['threshold']
            # we don't want to scan when drawing
            if editMode:
                params['output'] = ""
            else:
                del params['output']
        elif editMode:
            params['draw_output'] = ""

        if self.calib_matrix:
            params['calib_matrix'] = self.calib_matrix
        if self.scan['elevation']:
            params['raster'] = self.scan['elevation']
        elif self.scan['region']:
            params['region'] = self.scan['region']
        if self.scan['trim_tolerance']:
            params['trim_tolerance'] = self.scan['trim_tolerance']

        # flags
        params['flags'] = ''
        if continuous:
            params['flags'] += 'l'
        if not editMode and not params['flags']:
            del params['flags']

        if self.settings['tangible']['analyses']['contours'] and 'output' in params:
            params['contours'] = self.settings['tangible']['analyses']['contours']
            params['contours_step'] = self.settings['tangible']['analyses']['contours_step']
        elif editMode:
            params['contours'] = ""
        # export PLY
        if 'output' in self.settings['tangible'] and self.settings['tangible']['output']['PLY'] and \
           self.settings['tangible']['output']['PLY_file'] and not self.settings['tangible']['drawing']['active']:
            params['ply'] = self.settings['tangible']['output']['PLY_file']
        elif editMode:
            params['ply'] = ""
        # export color
        if 'output' in self.settings['tangible'] and self.settings['tangible']['output']['color'] and \
           self.settings['tangible']['output']['color_name']:
            params['color_output'] = self.settings['tangible']['output']['color_name']
            if self.sensor == 'k4a':
                params['camera_resolution'] = self.scan['camera_resolution']
                color_res = self.scan['color_resolution']
                if color_res:
                    params['color_resolution'] = float(color_res) / 1000

        elif editMode:
            params['color_output'] = ""

        trim_nsew = ','.join(self.scan['trim_nsewtb'].split(',')[:4])
        params['trim'] = trim_nsew
        if self.scan['smooth']:
            params['smooth_radius'] = float(self.scan['smooth']) / 1000
        if self.scan['interpolate']:
            method = 'interpolation'
        else:
            method = 'mean'
        params['method'] = method
        zrange = ','.join(self.scan['trim_nsewtb'].split(',')[4:])
        params['zrange'] = zrange
        params['rotate'] = self.scan['rotation_angle']
        params['resolution'] = float(self.scan['resolution']) / 1000
        params['zexag'] = self.scan['zexag']
        params['numscan'] = self.scan['numscans']
        if self.process and self.process.poll() is None:  # still running
            if self.resume_once is True:
                params['resume_once'] = ''
                self.resume_once = None

            if self.pause is True:
                params['pause'] = ''
            elif self.pause is False:
                params['resume'] = ''

        return params

    def EnableDataCatalogWatchdog(self, enable=True):
        """Disable/enable watchdog monitoring current mapset"""
        # TODO: improve when better API is available in GRASS
        try:
            tree = self.giface.lmgr.datacatalog.tree
            if enable:
                tree.ScheduleWatchCurrentMapset()
            else:
                observer = tree.observer
                if observer and observer.is_alive():
                    observer.stop()
                    observer.join()
                    observer.unschedule_all()
        except AttributeError:
            pass

    def IsScanning(self):
        if self.process and self.process.poll() is None:
            return True
        return False

    def Scan(self, continuous):
        if self.process and self.process.poll() is None:
            return
        self.status.SetLabel("Scanning...")
        wx.SafeYield()
        params = self.GatherParameters(editMode=False, continuous=continuous)
        self.process = gscript.start_command('r.in.kinect', overwrite=True, quiet=True,
                                             stdin=PIPE, signal_file=self._getSignalFile(), **params)
        return self.process

    def ScanOnce(self, event):
        # if already running, resume scanning one time
        if self.process and self.process.poll() is None:  # still running
            self.resume_once = True
            self.changedInput = True
        else:
            self.Scan(continuous=False)
            self.status.SetLabel("Importing scan...")
            self.process.communicate()
            self.process = None
            run_analyses(settings=self.settings, analysesFile=self.settings['tangible']['analyses']['file'],
                         giface=self.giface, update=self.OnUpdate, eventHandler=self, scanFilter=self.filter)
            self.status.SetLabel("Done.")
            self.OnUpdate(None)

    def RestartIfNotRunning(self, event):
        """Mechanism to restart scanning if process ends or
        to update scanning properties during running r.in.kinect
        if scanning input changed"""
        if self.process and self.process.poll() is not None:
            self.process.wait()
            self.process = None
            if self.observer:
                try:
                    self.observer.stop()
                except TypeError:  # throws error on mac
                    pass
                self.observer.join()
                self.observer = None
            self.Start()
        if self.changedInput:
            self.changedInput = False
            if self.process and self.process.poll() is None:
                params = self.GatherParameters(editMode=True, continuous=True)
                new_input = ["{}={}".format(key, params[key]) for key in params]
                self.process.stdin.write(gscript.encode('\n'.join(new_input) + '\n\n'))
                # flush needs to be there for Py3, alternative is to use Popen bufsize
                self.process.stdin.flush()
                # SIGUSR1 is the signal r.in.kinect looks for
                self.process.send_signal(signal.SIGUSR1)

    def Start(self):
        self.EnableDataCatalogWatchdog(False)
        self.Scan(continuous=True)
        self.status.SetLabel("Real-time scanning is running now.")

        if self.observer:
            return
        gisenv = gscript.gisenv()
        mapsetPath = os.path.join(gisenv['GISDBASE'], gisenv['LOCATION_NAME'], gisenv['MAPSET'])
        path2 = os.path.join(mapsetPath, 'vector')
        if not os.path.exists(path2):
            os.mkdir(os.path.join(mapsetPath, 'vector'))
        paths = [os.path.dirname(self._getSignalFile()), path2]
        handlers = [SignalFileChangeHandler(self.runImport, os.path.basename(self._getSignalFile())),
                    DrawingChangeHandler(self.runImportDrawing, self.settings['tangible']['drawing']['name'])]

        self.observer = Observer()
        for path, handler in zip(paths, handlers):
            self.observer.schedule(handler, path)

        self.observer.start()
        self.timer.Start(1000)

    def Stop(self):
        if self.process and self.process.poll() is None:  # still running
            self.process.terminate()
            self.process.communicate()
            self.process = None
            if self.observer:
                try:
                    self.observer.stop()
                except TypeError:  # throws error on mac
                    pass
                self.observer.join()
                self.observer = None
        self.timer.Stop()
        self.status.SetLabel("Real-time scanning stopped.")
        self.pause = False
        self.btnPause.SetLabel("Pause")
        self.EnableDataCatalogWatchdog(True)

    def Pause(self):
        if self.process and self.process.poll() is None:  # still running
            if not self.pause:
                self.pause = True
                self.btnPause.SetLabel("Resume")
            else:
                self.pause = False
                self.btnPause.SetLabel("Pause")
            self.changedInput = True

    def runImport(self):
        run_analyses(settings=self.settings, analysesFile=self.settings['tangible']['analyses']['file'],
                     giface=self.giface, update=self.OnUpdate, eventHandler=self, scanFilter=self.filter,
                     **self.additionalParams4Analyses)
        evt = updateGUIEvt(self.GetId())
        wx.PostEvent(self, evt)

    def runImportDrawing(self):
        self.drawing_panel.appendVector()
        run_analyses(settings=self.settings, analysesFile=self.settings['tangible']['analyses']['file'],
                     giface=self.giface, update=self.OnUpdate, eventHandler=self, scanFilter=self.filter,
                     **self.additionalParams4Analyses)
        evt = updateGUIEvt(self.GetId())
        wx.PostEvent(self, evt)

    def postEvent(self, receiver, event):
        wx.PostEvent(receiver, event)

    def OnAddLayers(self, event):
        if not self.giface.GetLayerTree():
            return
        ll = self.giface.GetLayerList()
        for each in event.layerSpecs:
            ll.AddLayer(**each)

    def OnRemoveLayers(self, event):
        if not self.giface.GetLayerTree():
            return
        ll = self.giface.GetLayerList()
        if not hasattr(ll, 'DeleteLayer'):
            print("Removing layers from layer Manager requires GRASS GIS version > 7.2")
            return
        for each in event.layers:
            ll.DeleteLayer(each)

    def OnCheckLayers(self, event):
        if not self.giface.GetLayerTree():
            return
        ll = self.giface.GetLayerList()
        if not hasattr(ll, 'CheckLayer'):
            print("Checking and unchecking layers in layer Manager requires GRASS GIS version > 7.2")
            return
        for each in event.layers:
            ll.CheckLayer(each, checked=event.checked)

    def OnSelectLayers(self, event):
        if not self.giface.GetLayerTree():
            return
        ll = self.giface.GetLayerList()
        if not hasattr(ll, 'SelectLayer'):
            print("Selecting layers in Layer Manager requires GRASS GIS version >= 7.6")
            return
        for each in event.layers:
            ll.SelectLayer(each, select=event.select)

    def OnChangeLayer(self, event):
        if not self.giface.GetLayerTree():
            return
        ll = self.giface.GetLayerList()
        if not hasattr(ll, 'ChangeLayer'):
            print("Changing layer in Layer Manager requires GRASS GIS version > 7.8")
            return
        params = {}
        if hasattr(event, 'ltype'):
            params['ltype'] = event.ltype
        if hasattr(event, 'cmd'):
            params['cmd'] = event.cmd
        if hasattr(event, 'opacity'):
            params['opacity'] = event.opacity
        ll.ChangeLayer(event.layer, **params)


def main(giface=None):
    global Observer, SignalFileChangeHandler, DrawingChangeHandler
    from watchdog.observers import Observer
    from change_handler import SignalFileChangeHandler, DrawingChangeHandler
    if wx.GetApp():
        dlg = TangibleLandscapePlugin(giface, parent=None)
        dlg.Show()
    else:
        from core.giface import StandaloneGrassInterface
        app = wx.App()
        dlg = TangibleLandscapePlugin(giface=StandaloneGrassInterface(), parent=None)
        dlg.Show()
        app.MainLoop()


if __name__ == '__main__':
    gscript.parser()
    from watchdog.observers import Observer
    from change_handler import SignalFileChangeHandler, DrawingChangeHandler
    main()
