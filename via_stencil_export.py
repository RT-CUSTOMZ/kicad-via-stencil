import pcbnew
import os
import wx
import tempfile
import shutil

class ViaStencilPlugin(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = "Via Stencil Exporter"
        self.category = "Export"
        self.description = "Generiert eine Schablone für Via-Plugging basierend auf dem aktuellen Layout."
        self.show_toolbar_button = True
        self.icon_file_name = os.path.join(os.path.dirname(__file__), 'icon.png')

    def Run(self):
        board = pcbnew.GetBoard()
        board_file = board.GetFileName()
        
        # Prüfung, ob die Datei gespeichert wurde
        if not board_file or not os.path.exists(board_file):
            wx.MessageBox("Das Layout muss vor dem Export gespeichert werden.\nBitte speichern Sie die Platine (Strg+S) und wiederholen Sie den Vorgang.", "Export abgebrochen", wx.OK | wx.ICON_WARNING)
            return
            
        temp_dir = tempfile.mkdtemp()
        temp_board_path = os.path.join(temp_dir, "temp_board.kicad_pcb")
        
        try:
            # Sicheres Kopieren in temporären Ordner (KiCad 10 Fix)
            shutil.copy2(board_file, temp_board_path)
            temp_board = pcbnew.LoadBoard(temp_board_path)
            
            items_to_remove = []
            
            # Alle Bauteile sammeln
            for fp in temp_board.Footprints():
                items_to_remove.append(fp)
                
            # Alle Zonen (Kupferflächen) sammeln
            for zone in temp_board.Zones():
                items_to_remove.append(zone)
                
            # Alle Zeichnungen sammeln (Edge.Cuts auf F.Cu verschieben)
            for drawing in temp_board.Drawings():
                if drawing.GetLayer() == pcbnew.Edge_Cuts:
                    drawing.SetLayer(pcbnew.F_Cu)
                else:
                    items_to_remove.append(drawing)
                    
            # Freie Texte sammeln (KiCad 10 spezifisch)
            if hasattr(temp_board, 'Texts'):
                for txt in temp_board.Texts():
                    items_to_remove.append(txt)
                    
            # Leiterbahnen sammeln, Vias anpassen
            for track in temp_board.Tracks():
                if isinstance(track, pcbnew.PCB_VIA):
                    drill = track.GetDrillValue()
                    track.SetWidth(drill) 
                else:
                    items_to_remove.append(track)
                    
            # Gesammelte Elemente auf einmal löschen
            for item in items_to_remove:
                temp_board.Remove(item)
                
            # SVG Plot starten
            pctl = pcbnew.PLOT_CONTROLLER(temp_board)
            popt = pctl.GetPlotOptions()
            
            out_dir = os.path.dirname(board_file)
            popt.SetOutputDirectory(out_dir)
            popt.SetFormat(pcbnew.PLOT_FORMAT_SVG)
            
            # Dynamischen Dateinamen basierend auf dem Projektnamen generieren
            board_basename = os.path.basename(board_file)
            board_name_no_ext = os.path.splitext(board_basename)[0]
            export_filename = f"{board_name_no_ext}_ViaStencil"
            
            pctl.SetLayer(pcbnew.F_Cu)
            pctl.OpenPlotfile(export_filename, pcbnew.PLOT_FORMAT_SVG, "Via Stencil Export")
            pctl.PlotLayer()
            pctl.ClosePlot()
            
            # Professionelle Erfolgsmeldung
            wx.MessageBox(f"Der Export wurde erfolgreich abgeschlossen.\n\nDatei: {export_filename}.svg\nVerzeichnis: {out_dir}", "Export erfolgreich", wx.OK | wx.ICON_INFORMATION)
            
        except Exception as e:
            wx.MessageBox(f"Während des Exports ist ein unerwarteter Fehler aufgetreten:\n{str(e)}", "Export fehlgeschlagen", wx.OK | wx.ICON_ERROR)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

ViaStencilPlugin().register()
